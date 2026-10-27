import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.local_job_analysis_store import (
    LocalAnalysisStateError, LocalJobAnalysisStore, maintain_analysis_lease,
)


FIRST_ID = "7d7afc23-e5f7-42a1-b571-755202eb7f83"
SECOND_ID = "0acc9131-0eeb-4493-bd2a-8a54a6a8996e"


class LocalJobAnalysisStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "analyses"
        self.store = LocalJobAnalysisStore(self.directory)
        self.data = {
            "id": {"value": FIRST_ID, "evidence": [{"source_field": "id", "quote": FIRST_ID}]},
            "compensation": [{"value": "$100,000 per year", "evidence": []}],
        }

    def succeed(self, data=None):
        self.store.enqueue(FIRST_ID)
        attempt = self.store.claim(FIRST_ID)
        return self.store.finish(FIRST_ID, attempt, data=data or self.data)

    def test_enqueue_persists_and_deduplicates_across_reopening(self):
        first = self.store.enqueue(FIRST_ID.upper())
        reopened = LocalJobAnalysisStore(self.directory)
        self.assertEqual(first, reopened.enqueue(FIRST_ID))
        self.assertEqual(first["job_posting_id"], FIRST_ID)
        self.assertEqual(set(first), {"job_posting_id", "status", "structured_data", "error_message"})
        self.assertEqual(first["status"], "queued")
        self.assertIsNone(first["structured_data"])
        self.assertIsNone(reopened.get(SECOND_ID))

    def test_enqueue_many_adds_only_missing_jobs_without_resetting_existing(self):
        self.succeed()
        self.assertEqual(self.store.enqueue_many([FIRST_ID, SECOND_ID, SECOND_ID]), 1)
        self.assertEqual(self.store.get(FIRST_ID)["status"], "succeeded")
        self.assertEqual(self.store.enqueue_many([FIRST_ID, SECOND_ID]), 0)
        self.assertEqual(self.store.get(SECOND_ID)["status"], "queued")

    def test_enqueue_many_rolls_back_whole_batch_on_invalid_id(self):
        with self.assertRaises(ValueError):
            self.store.enqueue_many([FIRST_ID, "invalid-uuid"])
        self.assertIsNone(self.store.get(FIRST_ID))

    def test_next_queued_returns_insertion_order_then_none(self):
        self.assertIsNone(self.store.next_queued_id())
        self.store.enqueue_many([FIRST_ID, SECOND_ID])
        self.assertEqual(self.store.next_queued_id(), FIRST_ID)
        self.store.claim(FIRST_ID)
        self.assertEqual(self.store.next_queued_id(), SECOND_ID)
        self.store.claim(SECOND_ID)
        self.assertIsNone(self.store.next_queued_id())

    def test_force_enqueue_retries_finished_jobs_and_retains_previous_result(self):
        self.succeed()
        result = self.store.enqueue(FIRST_ID, force=True)
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["structured_data"], self.data)
        attempt = self.store.claim(FIRST_ID)
        self.store.finish(FIRST_ID, attempt, error_message="Mock failure")
        result = self.store.enqueue(FIRST_ID, force=True)
        self.assertEqual(result["status"], "queued")
        self.assertIsNone(result["error_message"])

    def test_claim_never_steals_running_job_even_with_force(self):
        self.assertIsNone(self.store.claim(FIRST_ID))
        self.store.enqueue(FIRST_ID)
        attempt = self.store.claim(FIRST_ID)
        self.assertIsNotNone(attempt)
        self.assertIsNone(self.store.claim(FIRST_ID, force=True))
        self.assertEqual(self.store.enqueue(FIRST_ID, force=True)["status"], "running")
        self.store.finish(FIRST_ID, attempt, data=self.data)
        self.assertIsNone(self.store.claim(FIRST_ID))
        self.assertIsNotNone(self.store.claim(FIRST_ID, force=True))

    def test_concurrent_store_connections_allow_only_one_claim(self):
        self.store.enqueue(FIRST_ID)
        second_store = LocalJobAnalysisStore(self.directory)
        barrier = threading.Barrier(2)

        def claim(store):
            barrier.wait(timeout=5)
            return store.claim(FIRST_ID)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(claim, store) for store in (self.store, second_store)]
            claims = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(attempt is not None for attempt in claims), 1)

    def test_success_exports_plain_json_without_changing_content_or_dollar(self):
        result = self.succeed()
        exported = self.directory / "results" / f"{FIRST_ID}.json"
        self.assertEqual(result["structured_data"], self.data)
        self.assertEqual(json.loads(exported.read_text(encoding="utf-8")), self.data)
        self.assertIn('"$100,000 per year"', exported.read_text(encoding="utf-8"))
        self.assertEqual(list(exported.parent.glob("*.tmp")), [])

    def test_failed_refresh_preserves_previous_json_and_file(self):
        self.succeed()
        exported = self.directory / "results" / f"{FIRST_ID}.json"
        original_bytes = exported.read_bytes()
        attempt = self.store.claim(FIRST_ID, force=True)
        result = self.store.finish(FIRST_ID, attempt, error_message="Mock failure")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["structured_data"], self.data)
        self.assertEqual(result["error_message"], "Mock failure")
        self.assertEqual(exported.read_bytes(), original_bytes)

    def test_expired_attempt_cannot_finish_or_overwrite_new_attempt(self):
        self.store.enqueue(FIRST_ID)
        first_attempt = self.store.claim(FIRST_ID)
        self.store.finish(FIRST_ID, first_attempt, error_message="Mock failure")
        second_attempt = self.store.claim(FIRST_ID, force=True)
        with self.assertRaises(LocalAnalysisStateError):
            self.store.finish(FIRST_ID, first_attempt, data=self.data)
        self.assertEqual(self.store.get(FIRST_ID)["status"], "running")
        self.store.finish(FIRST_ID, second_attempt, data=self.data)
        with self.assertRaises(LocalAnalysisStateError):
            self.store.finish(FIRST_ID, second_attempt, error_message="Late failure")

    def test_export_failure_raises_and_does_not_claim_success(self):
        self.succeed()
        exported = self.directory / "results" / f"{FIRST_ID}.json"
        original_bytes = exported.read_bytes()
        attempt = self.store.claim(FIRST_ID, force=True)
        with patch("app.services.local_job_analysis_store.os.replace", side_effect=OSError("Disk failure")):
            with self.assertRaisesRegex(OSError, "Disk failure"):
                self.store.finish(FIRST_ID, attempt, data={"changed": True})
        result = self.store.get(FIRST_ID)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["structured_data"], self.data)
        self.assertEqual(exported.read_bytes(), original_bytes)
        self.assertEqual(list(exported.parent.glob("*.tmp")), [])

    def test_store_rejects_connection_strings_and_invalid_finish_arguments(self):
        with self.assertRaises(TypeError):
            LocalJobAnalysisStore("postgresql://not-a-local-directory")
        self.store.enqueue(FIRST_ID)
        attempt = self.store.claim(FIRST_ID)
        with self.assertRaises(ValueError):
            self.store.finish(FIRST_ID, attempt)
        with self.assertRaises(ValueError):
            self.store.finish(FIRST_ID, attempt, data=self.data, error_message="failure")
        self.assertEqual(self.store.get(FIRST_ID)["status"], "running")


class LocalJobAnalysisRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "analyses"
        self.now = 1000.0
        self.store = LocalJobAnalysisStore(
            self.directory, lease_seconds=30.0, clock=lambda: self.now
        )

    def claim(self, id=FIRST_ID):
        self.store.enqueue(id)
        return self.store.claim(id)

    def state(self, id=FIRST_ID):
        with closing(sqlite3.connect(self.store.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            return dict(connection.execute(
                "SELECT * FROM local_job_analyses WHERE job_posting_id = ?", (id,)
            ).fetchone())

    def test_claim_records_local_lease_without_changing_public_envelope(self):
        attempt = self.claim()
        state = self.state()
        self.assertEqual(state["attempt"], attempt)
        self.assertEqual(state["lease_expires_at"], 1030.0)
        self.assertEqual(set(self.store.get(FIRST_ID)), {
            "job_posting_id", "status", "structured_data", "error_message"
        })

    def test_renew_extends_only_live_matching_owner(self):
        attempt = self.claim()
        self.now = 1020.0
        self.assertFalse(self.store.renew(FIRST_ID, "not-the-owner"))
        self.assertTrue(self.store.renew(FIRST_ID, attempt))
        self.assertEqual(self.state()["lease_expires_at"], 1050.0)
        self.now = 1031.0
        self.assertEqual(self.store.recover_interrupted(), 0)
        self.store.finish(FIRST_ID, attempt, data={"valid": True})
        self.assertFalse(self.store.renew(FIRST_ID, attempt))
        self.assertIsNone(self.state()["lease_expires_at"])

    def test_expired_lease_cannot_renew_or_finish_before_recovery(self):
        attempt = self.claim()
        self.now = 1030.0
        self.assertFalse(self.store.renew(FIRST_ID, attempt))
        with self.assertRaises(LocalAnalysisStateError):
            self.store.finish(FIRST_ID, attempt, data={"late": True})
        self.assertFalse((self.directory / "results" / f"{FIRST_ID}.json").exists())
        self.assertEqual(self.store.get(FIRST_ID)["status"], "running")

    def test_recovery_only_requeues_expired_running_jobs_once(self):
        first_attempt = self.claim()
        self.now = 1020.0
        second_attempt = self.claim(SECOND_ID)
        self.now = 1031.0
        self.assertEqual(self.store.recover_interrupted(), 1)
        self.assertEqual(self.store.get(FIRST_ID)["status"], "queued")
        self.assertIn("interrupted", self.store.get(FIRST_ID)["error_message"])
        self.assertEqual(self.store.get(SECOND_ID)["status"], "running")
        self.assertEqual(self.state(SECOND_ID)["attempt"], second_attempt)
        self.assertIsNone(self.state()["attempt"])
        self.assertIsNone(self.state()["lease_expires_at"])
        self.assertEqual(self.store.recover_interrupted(), 0)
        new_attempt = self.store.claim(FIRST_ID)
        self.assertNotEqual(first_attempt, new_attempt)
        self.assertFalse(self.store.renew(FIRST_ID, first_attempt))
        self.assertFalse(self.store.release(FIRST_ID, first_attempt))
        with self.assertRaises(LocalAnalysisStateError):
            self.store.finish(FIRST_ID, first_attempt, data={"late": True})
        self.store.finish(FIRST_ID, new_attempt, data={"fresh": True})

    def test_recovery_can_target_one_job_without_recovering_others(self):
        self.claim()
        self.claim(SECOND_ID)
        self.now = 1031.0
        self.assertEqual(self.store.recover_interrupted(job_posting_id=FIRST_ID), 1)
        self.assertEqual(self.store.get(FIRST_ID)["status"], "queued")
        self.assertEqual(self.store.get(SECOND_ID)["status"], "running")
        self.assertEqual(self.store.recover_interrupted(job_posting_id=FIRST_ID), 0)
        self.assertEqual(self.store.recover_interrupted(), 1)

    def test_recovery_preserves_succeeded_failed_and_queued_jobs(self):
        attempt = self.claim()
        self.store.finish(FIRST_ID, attempt, data={"committed": True})
        attempt = self.claim(SECOND_ID)
        self.store.finish(SECOND_ID, attempt, error_message="Model returned invalid JSON")
        third_id = "04f9bc9e-5060-44f6-bba5-f55838efc627"
        self.store.enqueue(third_id)
        before = [self.store.get(id) for id in (FIRST_ID, SECOND_ID, third_id)]
        self.now = 2000.0
        self.assertEqual(self.store.recover_interrupted(), 0)
        self.assertEqual(before, [self.store.get(id) for id in (FIRST_ID, SECOND_ID, third_id)])

    def test_interrupted_refresh_restores_last_committed_export(self):
        committed = {"compensation": "$100,000", "version": "committed"}
        attempt = self.claim()
        self.store.finish(FIRST_ID, attempt, data=committed)
        self.store.claim(FIRST_ID, force=True)
        exported = self.directory / "results" / f"{FIRST_ID}.json"
        exported.write_text('{"version": "uncommitted"}', encoding="utf-8")
        self.now = 1031.0
        self.assertEqual(self.store.recover_interrupted(), 1)
        self.assertEqual(json.loads(exported.read_text(encoding="utf-8")), committed)
        self.assertEqual(self.store.get(FIRST_ID)["structured_data"], committed)
        new_attempt = self.store.claim(FIRST_ID)
        self.store.finish(FIRST_ID, new_attempt, error_message="Mock failure")
        self.assertEqual(json.loads(exported.read_text(encoding="utf-8")), committed)

    def test_interrupted_first_attempt_removes_uncommitted_export(self):
        self.claim()
        exported = self.directory / "results" / f"{FIRST_ID}.json"
        exported.write_text('{"uncommitted": true}', encoding="utf-8")
        self.now = 1031.0
        self.assertEqual(self.store.recover_interrupted(), 1)
        self.assertFalse(exported.exists())
        self.assertIsNone(self.store.get(FIRST_ID)["structured_data"])

    def test_recovery_rolls_back_if_export_cannot_be_restored(self):
        attempt = self.claim()
        self.store.finish(FIRST_ID, attempt, data={"committed": True})
        attempt = self.store.claim(FIRST_ID, force=True)
        self.now = 1031.0
        with patch.object(self.store, "_write_result", side_effect=OSError("Disk unavailable")):
            with self.assertRaises(OSError):
                self.store.recover_interrupted()
        self.assertEqual(self.store.get(FIRST_ID)["status"], "running")
        self.assertEqual(self.state()["attempt"], attempt)

    def test_release_requeues_owned_attempt_and_preserves_committed_result(self):
        attempt = self.claim()
        self.store.finish(FIRST_ID, attempt, data={"committed": True})
        attempt = self.store.claim(FIRST_ID, force=True)
        exported = self.directory / "results" / f"{FIRST_ID}.json"
        exported.write_text('{"uncommitted": true}', encoding="utf-8")
        self.assertFalse(self.store.release(FIRST_ID, "not-the-owner"))
        self.assertTrue(self.store.release(FIRST_ID, attempt))
        self.assertEqual(self.store.get(FIRST_ID)["status"], "queued")
        self.assertIsNone(self.state()["lease_expires_at"])
        self.assertFalse(self.store.release(FIRST_ID, attempt))
        self.assertEqual(json.loads(exported.read_text(encoding="utf-8")), {"committed": True})
        self.assertFalse(self.store.renew(FIRST_ID, attempt))
        with self.assertRaises(LocalAnalysisStateError):
            self.store.finish(FIRST_ID, attempt, data={"late": True})

    def test_owned_expired_attempt_can_release_without_waiting_for_scan(self):
        attempt = self.claim()
        self.now = 1031.0
        self.assertTrue(self.store.release(FIRST_ID, attempt))
        self.assertEqual(self.store.get(FIRST_ID)["status"], "queued")

    def test_local_legacy_queue_upgrades_and_recovers_only_legacy_running(self):
        legacy_directory = Path(self.temporary.name) / "legacy"
        legacy_directory.mkdir()
        database = legacy_directory / "queue.sqlite3"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("""CREATE TABLE local_job_analyses (
                job_posting_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                result_json TEXT, error_message TEXT, attempt TEXT
            )""")
            connection.execute(
                "INSERT INTO local_job_analyses VALUES (?, 'running', ?, NULL, 'old-attempt')",
                (FIRST_ID, '{"committed": true}'),
            )
            connection.execute(
                "INSERT INTO local_job_analyses VALUES (?, 'failed', NULL, 'old error', NULL)",
                (SECOND_ID,),
            )
        legacy = LocalJobAnalysisStore(legacy_directory, clock=lambda: self.now)
        self.assertEqual(legacy.recover_interrupted(), 0)
        self.now += 100.0
        reopened_before_expiry = LocalJobAnalysisStore(
            legacy_directory, clock=lambda: self.now
        )
        self.assertEqual(reopened_before_expiry.recover_interrupted(), 0)
        self.now += 21.0
        self.assertEqual(legacy.recover_interrupted(), 1)
        self.assertEqual(legacy.get(FIRST_ID)["status"], "queued")
        self.assertEqual(legacy.get(FIRST_ID)["structured_data"], {"committed": True})
        self.assertEqual(legacy.get(SECOND_ID)["status"], "failed")
        self.assertEqual(legacy.get(SECOND_ID)["error_message"], "old error")
        reopened = LocalJobAnalysisStore(legacy_directory)
        self.assertEqual(reopened.recover_interrupted(), 0)
        exported = legacy_directory / "results" / f"{FIRST_ID}.json"
        self.assertEqual(json.loads(exported.read_text(encoding="utf-8")), {"committed": True})

    def test_renew_and_finish_sample_clock_after_acquiring_transaction(self):
        attempt = self.claim()
        original_transaction = self.store._transaction
        lock_acquired = False

        @contextmanager
        def transaction():
            nonlocal lock_acquired
            with original_transaction() as connection:
                lock_acquired = True
                try:
                    yield connection
                finally:
                    lock_acquired = False

        def clock():
            self.assertTrue(lock_acquired)
            return self.now

        self.store.clock = clock
        with patch.object(self.store, "_transaction", transaction):
            self.assertTrue(self.store.renew(FIRST_ID, attempt))
            self.store.finish(FIRST_ID, attempt, data={"valid": True})

    def test_invalid_lease_configuration_does_not_create_local_files(self):
        for lease in (0, -1, float("inf"), float("nan"), True, None):
            with self.subTest(lease=lease):
                bad_directory = Path(self.temporary.name) / "bad"
                with self.assertRaises(ValueError):
                    LocalJobAnalysisStore(bad_directory, lease_seconds=lease)
                self.assertFalse(bad_directory.exists())


# Lease maintenance is tested with bounded local thread waits.
class LocalAnalysisLeaseTests(unittest.TestCase):
    def test_healthy_heartbeat_renews_and_stops_when_work_exits(self):
        store = Mock(lease_seconds=0.03)
        renewed = threading.Event()
        threads = []

        def renew(job_id, attempt):
            threads.append(threading.current_thread())
            renewed.set()
            return True

        store.renew.side_effect = renew
        with maintain_analysis_lease(store, "job", "attempt") as ensure_owned:
            self.assertTrue(renewed.wait(timeout=2))
            ensure_owned()
        self.assertTrue(threads)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        store.renew.assert_called_with("job", "attempt")

    def test_lost_or_failed_heartbeat_prevents_export_without_disclosing_error(self):
        for outcome in (False, OSError("private path")):
            with self.subTest(outcome=type(outcome).__name__):
                store = Mock(lease_seconds=0.03)
                called = threading.Event()
                threads = []

                def renew(*_args):
                    threads.append(threading.current_thread())
                    called.set()
                    if isinstance(outcome, Exception):
                        raise outcome
                    return outcome

                store.renew.side_effect = renew
                with maintain_analysis_lease(store, "job", "attempt") as ensure_owned:
                    self.assertTrue(called.wait(timeout=2))
                    # Joining the completed heartbeat removes a timing race around
                    # the lost flag; the failed callback never retries or revives.
                    threads[0].join(timeout=2)
                    with self.assertRaisesRegex(LocalAnalysisStateError, "lease was lost") as error:
                        ensure_owned()
                    self.assertNotIn("private", str(error.exception))
                self.assertEqual(1, store.renew.call_count)

    def test_work_exception_still_stops_the_heartbeat(self):
        store = Mock(lease_seconds=0.03)
        renewed = threading.Event()
        threads = []

        def renew(*_args):
            threads.append(threading.current_thread())
            renewed.set()
            return True

        store.renew.side_effect = renew
        with self.assertRaises(KeyboardInterrupt):
            with maintain_analysis_lease(store, "job", "attempt"):
                self.assertTrue(renewed.wait(timeout=2))
                raise KeyboardInterrupt
        self.assertTrue(all(not thread.is_alive() for thread in threads))


if __name__ == "__main__":
    unittest.main()
