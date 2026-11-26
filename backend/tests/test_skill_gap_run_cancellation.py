"""Cancelling a deleted account's skill-gap runs. Local JSON store, blocking mock Agent; no DB or network."""
from pathlib import Path
import tempfile
from threading import Event, Lock
import unittest
from uuid import uuid4

from app.services.skill_gaps import runs
from tests.skill_gap_fixtures import (
    CONFIRMED_AT, RESUME_ID, USER_ID, absent_response, group_manager, reviewed_resume,
)


class RunCancellationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.entered, self.release = Event(), Event()
        self.paid_calls: list[str] = []
        self._calls_lock = Lock()

        def invoke(payload, save, on_request, timings):
            # Block like a slow Agent, then account for the request the way the real transport does.
            self.entered.set()
            self.assertTrue(self.release.wait(5), "test never released the Agent")
            on_request()
            with self._calls_lock:
                self.paid_calls.append(payload["evidence_scope"]["branch"])
            return absent_response(payload)

        self.manager = group_manager(self.directory, invoker=invoke)
        self.addCleanup(self.release.set)  # Never leave a worker blocked if a test fails early.
        self.addCleanup(self.manager.close)

    def submit(self, user_id=USER_ID, resume_id=RESUME_ID):
        return self.manager.submit(user_id=user_id, resume_id=resume_id, reviewed_resume=reviewed_resume(),
                                   filename="example.pdf", confirmed_at=CONFIRMED_AT,
                                   job_family="software_engineer")

    def finish(self) -> None:
        """Release the Agent and wait until the worker queue is empty."""
        self.release.set()
        self.manager.close()

    def test_running_run_stops_before_the_paid_call_and_leaves_no_files(self) -> None:
        run = self.submit()
        self.assertTrue(self.entered.wait(5))
        cache_folder = self.manager.branch_cache.owner_folder(str(USER_ID))
        (cache_folder / "entry.json").parent.mkdir(parents=True, exist_ok=True)
        (cache_folder / "entry.json").write_text("{}", encoding="utf-8")

        self.assertEqual([run.id], self.manager.forget_user(USER_ID))
        self.finish()

        self.assertEqual([], self.paid_calls)
        self.assertFalse((self.directory / run.id).exists())
        self.assertFalse(cache_folder.exists())
        self.assertEqual({}, self.manager._cancelled)
        with self.assertRaises(KeyError):
            self.manager.get(run.id, user_id=USER_ID)

    def test_queued_run_never_starts_and_other_users_are_untouched(self) -> None:
        other_user, other_resume = uuid4(), uuid4()
        other = self.submit(user_id=other_user, resume_id=other_resume)  # Occupies the single worker.
        self.assertTrue(self.entered.wait(5))
        queued = self.submit()

        self.assertEqual([queued.id], self.manager.forget_user(USER_ID))
        self.finish()

        self.assertFalse((self.directory / queued.id).exists())
        finished = self.manager.get(other.id, user_id=other_user)
        self.assertEqual("completed", finished.status)
        self.assertTrue((self.directory / other.id / "skill_gaps.json").exists())
        self.assertTrue(self.paid_calls)
        self.assertNotIn(queued.id, self.manager._states)

    def test_finished_runs_are_forgotten_but_not_cancelled(self) -> None:
        self.release.set()
        run = self.submit()
        self.manager.close()
        self.assertEqual("completed", self.manager.get(run.id, user_id=USER_ID).status)

        self.assertEqual([], self.manager.forget_user(USER_ID))

        self.assertNotIn(run.id, self.manager._states)
        self.assertNotIn(run.id, self.manager._keys.values())
        # Finished runs' files are removed by account deletion's local cleanup, not by the worker.
        self.assertTrue((self.directory / run.id).exists())


class ForgetUserRunsTests(unittest.TestCase):
    def test_does_not_create_a_manager_just_to_forget(self) -> None:
        runs._cached_skill_gap_run_manager.cache_clear()
        self.addCleanup(runs._cached_skill_gap_run_manager.cache_clear)

        self.assertEqual([], runs.forget_user_runs(uuid4()))
        self.assertEqual(0, runs._cached_skill_gap_run_manager.cache_info().currsize)


if __name__ == "__main__":
    unittest.main()
