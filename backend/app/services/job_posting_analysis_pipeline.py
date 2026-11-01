"""Read JP data without remote writes; validate and save analysis results locally."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import event, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.job_posting import JobPosting
from app.schemas.job_posting_analysis import (
    JobPostingAnalysisValidationError,
    validate_analysis_response,
)
from app.services.job_posting_analysis_agent import (
    JobPostingAnalysisAgentError,
    JobPostingAnalysisContentValidationError,
    JobPostingAnalysisInputError,
    validate_analysis_content,
)
from app.services.local_job_analysis_store import (
    LocalAnalysisStateError,
    LocalJobAnalysisStore,
    maintain_analysis_lease,
)


# This is a conservative pre-Agent spending guard, not job_family classification.
# Qualifiers before/after the phrase are allowed; synonyms are not inferred.
_FOCUS_TITLE = re.compile(
    r"\b(?:software[\s\-\u2010-\u2015]+engineer|"
    r"data[\s\-\u2010-\u2015]+analyst|ai[\s\-\u2010-\u2015]+engineer)\b",
    re.IGNORECASE,
)


def is_focus_job_title(title: Any) -> bool:
    return isinstance(title, str) and _FOCUS_TITLE.search(title) is not None


class JobPostingNotFoundError(LookupError):
    """The source posting does not exist."""


class JobPostingSourceReadOnlyError(RuntimeError):
    """A non-SELECT statement was attempted through the JD source connection."""


def posting_id(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise JobPostingAnalysisInputError(
            "job_posting_id must be a valid UUID."
        ) from None


def serialize_posting(posting: JobPosting) -> dict[str, Any]:
    """Preserve every raw posting column, with JSON-ready UUIDs and timestamps."""
    result: dict[str, Any] = {}
    for column in inspect(JobPosting).columns:
        value = getattr(posting, column.key)
        if isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        result[column.key] = value
    return result


def _select_only(connection, cursor, statement, parameters, context, executemany):
    # These source queries use SQLAlchemy SELECTs only; rejecting everything else
    # also prevents accidental flushes or later changes from writing through here.
    compiled_statement = getattr(getattr(context, "compiled", None), "statement", None)
    if not getattr(compiled_statement, "is_select", False):
        raise JobPostingSourceReadOnlyError(
            "The JD source connection only permits SELECT statements."
        )


class ReadOnlyJobPostingSource:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with self.session_factory() as session, session.no_autoflush:
            connection = session.connection()
            dialect = connection.dialect.name
            if dialect == "postgresql":
                # This affects this transaction only, never the role or database.
                # It runs before any source query, and fails closed if unsupported.
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            elif dialect != "sqlite":
                raise NotImplementedError(
                    "Read-only JD access supports PostgreSQL and SQLite."
                )
            event.listen(connection, "before_cursor_execute", _select_only)
            try:
                yield session
            finally:
                # Connection-local only: do not leak a hook to pooled connections
                # or impose JD read restrictions on the existing scraper.
                event.remove(connection, "before_cursor_execute", _select_only)

    def get_posting(self, job_posting_id: UUID | str) -> dict[str, Any]:
        job_id = posting_id(job_posting_id)
        with self._session() as session:
            posting = session.scalar(select(JobPosting).where(JobPosting.id == job_id))
            if posting is None:
                raise JobPostingNotFoundError("The source job posting was not found.")
            return serialize_posting(posting)

    def get_titles(self, job_ids: list[str]) -> dict[str, str | None]:
        """Read only titles for a local queue snapshot, in bounded SELECT batches."""
        ids = [posting_id(job_id) for job_id in job_ids]
        titles: dict[str, str | None] = {}
        for start in range(0, len(ids), 500):
            query = select(JobPosting.id, JobPosting.title).where(
                JobPosting.id.in_(ids[start:start + 500])
            )
            with self._session() as session:
                rows = list(session.execute(query))
            titles.update((str(row.id), row.title) for row in rows)
        return titles

    def iter_ids(self, batch_size: int = 500, *, focused_only: bool = False) -> Iterator[str]:
        """Page through source IDs, closing each session before yielding its IDs.

        A later scan discovers any newly inserted IDs, including ones ordered
        before the current cursor. Analysis results and task state stay local.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise JobPostingAnalysisInputError("batch_size must be a positive integer.")
        previous: UUID | None = None
        while True:
            columns = (JobPosting.id, JobPosting.title) if focused_only else (JobPosting.id,)
            query = select(*columns).order_by(JobPosting.id).limit(batch_size)
            if previous is not None:
                query = query.where(JobPosting.id > previous)
            with self._session() as session:
                if focused_only:
                    rows = list(session.execute(query))
                    ids = [row.id for row in rows]
                    eligible = {row.id for row in rows if is_focus_job_title(row.title)}
                else:
                    ids = list(session.scalars(query))
                    eligible = None
            if not ids:
                return
            for job_id in ids:
                if eligible is None or job_id in eligible:
                    yield str(job_id)
            if len(ids) < batch_size:
                return
            previous = ids[-1]


# Reserved future save boundary; no active pipeline path calls this function.
class SupabaseAnalysisPersistenceNotEnabled(NotImplementedError):
    """The future remote result destination has not been implemented."""


def save_analysis_to_supabase(
    *, job_posting_id: str, structured_data: dict[str, Any]
) -> None:
    """Refuse remote persistence without inspecting or changing the 28 fields.

    This is intentionally disconnected from the active pipeline and dependency
    factory. It must not silently report success or fall back to remote writes.
    """
    raise SupabaseAnalysisPersistenceNotEnabled(
        "Supabase analysis persistence is not enabled; keep results in local storage."
    )


JobPostingAnalysisStateError = LocalAnalysisStateError


class PostingAnalysisAgent(Protocol):
    def analyze(self, posting: dict[str, Any]) -> dict[str, Any]: ...


class JobPostingAnalysisPipeline:
    def __init__(
        self,
        source: ReadOnlyJobPostingSource,
        store: LocalJobAnalysisStore,
        agent: PostingAnalysisAgent,
    ) -> None:
        self.source = source
        self.store = store
        self.agent = agent
        self._skipped_focus_ids: set[str] = set()

    def get_posting(self, job_posting_id: UUID | str) -> dict[str, Any]:
        return self.source.get_posting(job_posting_id)

    def get_analysis(self, job_posting_id: UUID | str) -> dict[str, Any] | None:
        return self.store.get(str(posting_id(job_posting_id)))

    def enqueue(self, job_posting_id: UUID | str, *, force: bool = False) -> dict[str, Any]:
        job_id = str(posting_id(job_posting_id))
        if self.store.get(job_id) is None:
            # A direct request must identify an existing source posting.
            self.source.get_posting(job_id)
        return self.store.enqueue(job_id, force=force)

    def enqueue_missing(
        self, *, batch_size: int = 500, limit: int | None = None,
        focused_only: bool = False,
    ) -> int:
        """First scan backfills; later scans add only IDs absent from the local queue.

        No timestamp watermark is used. Repeated scans also discover late-arriving
        IDs and never reset successful, failed, queued or running analyses.
        """
        for name, value in (("batch_size", batch_size), ("limit", limit)):
            if value is None and name == "limit":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise JobPostingAnalysisInputError(f"{name} must be a positive integer.")
        added = 0
        batch: list[str] = []
        for job_id in self.source.iter_ids(batch_size=batch_size, focused_only=focused_only):
            batch.append(job_id)
            capacity = min(batch_size, limit - added) if limit is not None else batch_size
            if len(batch) >= capacity:
                added += self.store.enqueue_many(batch)
                batch.clear()
                if limit is not None and added >= limit:
                    return added
        if batch:
            added += self.store.enqueue_many(batch)
        return added

    def recover_interrupted(self) -> int:
        """Start a new worker scan and recover expired attempts locally.

        Reevaluating skipped titles once per scan permits source title changes
        without rereading an unrelated legacy queue on every short idle poll.
        """
        self._skipped_focus_ids.clear()
        return self.store.recover_interrupted()

    def process_next(self, *, focused_only: bool = False) -> dict[str, Any] | None:
        if not focused_only:
            job_id = self.store.next_queued_id()
            return self.analyze(job_id) if job_id is not None else None
        # Existing queues may predate the spending guard or contain manual API
        # requests. Leave unrelated rows queued, without blocking eligible rows.
        candidates = [
            job_id for job_id in self.store.queued_ids()
            if job_id not in self._skipped_focus_ids
        ]
        titles = self.source.get_titles(candidates)
        self._skipped_focus_ids.update(
            job_id for job_id, title in titles.items() if not is_focus_job_title(title)
        )
        for job_id in candidates:
            if job_id not in self._skipped_focus_ids:
                # Missing source IDs follow the normal terminal failure path.
                return self.analyze(job_id, focused_only=True)
        return None

    def analyze(
        self, job_posting_id: UUID | str, *, force: bool = False,
        focused_only: bool = False,
    ) -> dict[str, Any]:
        job_id = str(posting_id(job_posting_id))
        self.store.recover_interrupted(job_posting_id=job_id)
        self.enqueue(job_id)
        attempt = self.store.claim(job_id, force=force)
        if attempt is None:
            result = self.store.get(job_id)
            if result is None:
                raise LocalAnalysisStateError("The local analysis record is unavailable.")
            return result

        try:
            with maintain_analysis_lease(self.store, job_id, attempt) as ensure_owned:
                return self._analyze_claimed(job_id, attempt, ensure_owned, focused_only=focused_only)
        except BaseException as error:
            # A graceful interrupt releases only this attempt. Abrupt exits are
            # recovered after lease expiry by a later worker scan or API request.
            if not isinstance(error, Exception):
                try:
                    self.store.release(job_id, attempt)
                except Exception:
                    # Preserve the original interrupt; expiry can still recover it.
                    pass
            raise

    def _analyze_claimed(
        self, job_id: str, attempt: str, ensure_owned: Callable[[], None],
        *, focused_only: bool = False,
    ) -> dict[str, Any]:
        try:
            posting = self.source.get_posting(job_id)
        except JobPostingNotFoundError:
            # A source deleted after enqueue must not permanently block the queue.
            ensure_owned()
            return self.store.finish(
                job_id, attempt, error_message="The source job posting was not found."
            )
        except SQLAlchemyError:
            # Nothing was analyzed and outages are often brief (e.g. a pooler
            # refusal). A failed row is never requeued, so keep this one queued.
            ensure_owned()
            self.store.release(job_id, attempt)
            raise
        except JobPostingSourceReadOnlyError:
            # A rejected non-SELECT is a code defect that repeats on every retry.
            ensure_owned()
            self.store.finish(
                job_id, attempt, error_message="The source job posting could not be read."
            )
            raise

        # The source session has closed; only local state changes from this point.
        ensure_owned()
        if focused_only and not is_focus_job_title(posting.get("title")):
            # The title may have changed after discovery/selection. Never spend
            # an Agent run on an out-of-scope snapshot; preserve the queued row.
            self.store.release(job_id, attempt)
            self._skipped_focus_ids.add(job_id)
            result = self.store.get(job_id)
            if result is None:
                raise LocalAnalysisStateError("The local analysis record is unavailable.")
            return result
        try:
            # Validate against the original snapshot even if an Agent adapter mutates its input.
            result = self.agent.analyze(deepcopy(posting))
            try:
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError, RecursionError):
                raise JobPostingAnalysisValidationError("Invalid analysis JSON.") from None
            validated = validate_analysis_response(encoded, job_posting_id=job_id)
            validate_analysis_content(validated, posting=posting)
        except Exception as error:
            if isinstance(error, JobPostingAnalysisContentValidationError):
                message = str(error)
            elif isinstance(error, JobPostingAnalysisValidationError):
                message = "The Agent returned an invalid job analysis result."
            elif isinstance(error, JobPostingAnalysisInputError):
                message = "The source posting is not valid for job analysis."
            elif isinstance(error, JobPostingAnalysisAgentError):
                message = "The job analysis Agent request failed."
            else:
                message = "The job analysis attempt failed."
            ensure_owned()
            return self.store.finish(job_id, attempt, error_message=message)

        # An expired or lost attempt cannot export, even if its Agent returns late.
        ensure_owned()
        return self.store.finish(job_id, attempt, data=validated)
