"""Local-only analysis queue, leased ownership, and recoverable JSON exports.

Only local SQLite is upgraded here. Legacy running rows receive one lease grace
period on upgrade; stop pre-upgrade workers before using this version so they
cannot write without lease fencing.
SQLite is the committed source of truth if a crash interrupts the JSON export.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from typing import Any


class LocalAnalysisStateError(RuntimeError):
    """An attempt no longer owns an unexpired running local analysis."""


class LocalJobAnalysisStore:
    def __init__(
        self,
        directory: Path,
        *,
        lease_seconds: float = 120.0,
        clock: Callable[[], float] = time.time,
    ):
        if not isinstance(directory, Path):
            raise TypeError("directory must be a local pathlib.Path")
        if isinstance(lease_seconds, bool):
            raise ValueError("lease_seconds must be positive and finite")
        try:
            lease_seconds = float(lease_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("lease_seconds must be positive and finite") from exc
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive and finite")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.lease_seconds = lease_seconds
        self.clock = clock
        self.directory = directory
        self.results_directory = directory / "results"
        self.database_path = directory / "queue.sqlite3"
        self.results_directory.mkdir(parents=True, exist_ok=True)
        with self._transaction() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS local_job_analyses (
                    job_posting_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (
                        status IN ('queued', 'running', 'succeeded', 'failed')
                    ),
                    result_json TEXT,
                    error_message TEXT,
                    attempt TEXT,
                    lease_expires_at REAL
                )"""
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(local_job_analyses)")
            }
            if "lease_expires_at" not in columns:
                connection.execute(
                    "ALTER TABLE local_job_analyses ADD COLUMN lease_expires_at REAL"
                )
                connection.execute(
                    "UPDATE local_job_analyses SET lease_expires_at = ? "
                    "WHERE status = 'running' AND lease_expires_at IS NULL",
                    (self._now() + self.lease_seconds,),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30.0, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _now(self) -> float:
        now = float(self.clock())
        if not math.isfinite(now):
            raise ValueError("clock must return a finite timestamp")
        return now

    @staticmethod
    def _id(job_posting_id: str) -> str:
        return str(uuid.UUID(job_posting_id))

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_posting_id": row["job_posting_id"],
            "status": row["status"],
            "structured_data": (
                json.loads(row["result_json"])
                if row["result_json"] is not None
                else None
            ),
            "error_message": row["error_message"],
        }

    def get(self, id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM local_job_analyses WHERE job_posting_id = ?",
                (self._id(id),),
            ).fetchone()
            return self._snapshot(row) if row is not None else None
        finally:
            connection.close()

    def enqueue(self, id: str, force: bool = False) -> dict[str, Any]:
        canonical_id = self._id(id)
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO local_job_analyses "
                "(job_posting_id, status) VALUES (?, 'queued')",
                (canonical_id,),
            )
            if force:
                connection.execute(
                    "UPDATE local_job_analyses SET status = 'queued', "
                    "error_message = NULL, attempt = NULL, lease_expires_at = NULL "
                    "WHERE job_posting_id = ? AND status IN ('failed', 'succeeded')",
                    (canonical_id,),
                )
            row = connection.execute(
                "SELECT * FROM local_job_analyses WHERE job_posting_id = ?",
                (canonical_id,),
            ).fetchone()
            return self._snapshot(row)

    def enqueue_many(self, ids: Iterable[str]) -> int:
        inserted = 0
        with self._transaction() as connection:
            for id in ids:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO local_job_analyses "
                    "(job_posting_id, status) VALUES (?, 'queued')",
                    (self._id(id),),
                )
                inserted += cursor.rowcount
        return inserted

    def next_queued_id(self) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT job_posting_id FROM local_job_analyses "
                "WHERE status = 'queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            return row["job_posting_id"] if row is not None else None
        finally:
            connection.close()

    def claim(self, id: str, force: bool = False) -> str | None:
        attempt = str(uuid.uuid4())
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE local_job_analyses SET status = 'running', "
                "attempt = ?, lease_expires_at = ?, error_message = NULL "
                "WHERE job_posting_id = ? "
                "AND (status = 'queued' OR (? AND status IN ('failed', 'succeeded')))",
                (attempt, self._now() + self.lease_seconds, self._id(id), force),
            )
            return attempt if cursor.rowcount == 1 else None

    def renew(self, id: str, attempt: str) -> bool:
        """Extend only this attempt's still-live lease; never revive an expired one."""
        with self._transaction() as connection:
            now = self._now()
            cursor = connection.execute(
                "UPDATE local_job_analyses SET lease_expires_at = ? "
                "WHERE job_posting_id = ? AND status = 'running' AND attempt = ? "
                "AND lease_expires_at > ?",
                (now + self.lease_seconds, self._id(id), attempt, now),
            )
            return cursor.rowcount == 1

    def _write_result(self, id: str, serialized: str) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.results_directory,
                prefix=f".{id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.results_directory / f"{id}.json")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _restore_committed_export(self, row: sqlite3.Row) -> None:
        """Undo an export written just before a crashed SQLite transaction."""
        if row["result_json"] is None:
            (self.results_directory / f'{row["job_posting_id"]}.json').unlink(
                missing_ok=True
            )
        else:
            self._write_result(row["job_posting_id"], row["result_json"] + "\n")

    def recover_interrupted(self, *, job_posting_id: str | None = None) -> int:
        """Requeue expired/legacy running attempts without touching live or failed jobs."""
        with self._transaction() as connection:
            query = (
                "SELECT * FROM local_job_analyses WHERE status = 'running' "
                "AND (lease_expires_at IS NULL OR lease_expires_at <= ?)"
            )
            parameters: tuple[Any, ...] = (self._now(),)
            if job_posting_id is not None:
                query += " AND job_posting_id = ?"
                parameters += (self._id(job_posting_id),)
            rows = connection.execute(query, parameters).fetchall()
            for row in rows:
                self._restore_committed_export(row)
                connection.execute(
                    "UPDATE local_job_analyses SET status = 'queued', attempt = NULL, "
                    "lease_expires_at = NULL, error_message = ? "
                    "WHERE job_posting_id = ?",
                    (
                        "Previous local analysis attempt was interrupted; queued for retry.",
                        row["job_posting_id"],
                    ),
                )
            return len(rows)

    def release(self, id: str, attempt: str) -> bool:
        """Requeue an interrupted owner immediately; a successor has a different token."""
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM local_job_analyses WHERE job_posting_id = ? "
                "AND status = 'running' AND attempt = ?",
                (self._id(id), attempt),
            ).fetchone()
            if row is None:
                return False
            self._restore_committed_export(row)
            connection.execute(
                "UPDATE local_job_analyses SET status = 'queued', attempt = NULL, "
                "lease_expires_at = NULL, error_message = ? WHERE job_posting_id = ?",
                (
                    "Local analysis attempt was interrupted; queued for retry.",
                    row["job_posting_id"],
                ),
            )
            return True

    def finish(
        self,
        id: str,
        attempt: str,
        *,
        data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if data is None and error_message is None:
            raise ValueError("Provide result data or an error message")
        if data is not None and error_message is not None:
            raise ValueError("A result cannot also contain an error message")
        if data is not None and not isinstance(data, dict):
            raise TypeError("result data must be a JSON object")
        canonical_id = self._id(id)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM local_job_analyses WHERE job_posting_id = ?",
                (canonical_id,),
            ).fetchone()
            if (
                row is None
                or row["status"] != "running"
                or row["attempt"] != attempt
                or row["lease_expires_at"] is None
                or row["lease_expires_at"] <= self._now()
            ):
                raise LocalAnalysisStateError(
                    "This attempt does not own an unexpired running job"
                )
            if data is not None:
                serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
                self._write_result(canonical_id, serialized + "\n")
                connection.execute(
                    "UPDATE local_job_analyses SET status = 'succeeded', "
                    "result_json = ?, error_message = NULL, attempt = NULL, "
                    "lease_expires_at = NULL WHERE job_posting_id = ?",
                    (serialized, canonical_id),
                )
            else:
                connection.execute(
                    "UPDATE local_job_analyses SET status = 'failed', "
                    "error_message = ?, attempt = NULL, lease_expires_at = NULL "
                    "WHERE job_posting_id = ?",
                    (error_message, canonical_id),
                )
            row = connection.execute(
                "SELECT * FROM local_job_analyses WHERE job_posting_id = ?",
                (canonical_id,),
            ).fetchone()
            return self._snapshot(row)


@contextmanager
def maintain_analysis_lease(
    store: LocalJobAnalysisStore, job_id: str, attempt: str
) -> Iterator[Callable[[], None]]:
    stop = Event()
    lost = Event()

    def ensure_owned() -> None:
        if lost.is_set():
            raise LocalAnalysisStateError("The local analysis lease was lost.")

    def heartbeat() -> None:
        while not stop.wait(store.lease_seconds / 3):
            try:
                renewed = store.renew(job_id, attempt)
            except Exception:
                # Local storage errors must not allow an unfenced export later.
                lost.set()
                return
            if not renewed:
                lost.set()
                return

    thread = Thread(target=heartbeat, name="jd-analysis-heartbeat", daemon=True)
    try:
        thread.start()
        yield ensure_owned
    finally:
        stop.set()
        # Each heartbeat uses a new SQLite connection with a 30-second busy limit.
        # Bound cleanup even if the local database or filesystem is unavailable.
        try:
            thread.join(timeout=35.0)
        except RuntimeError:
            # start() itself may have failed or been interrupted; stop is already set.
            pass
