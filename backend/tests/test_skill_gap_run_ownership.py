"""Local JSON lifecycle tests with a mock Agent and synthetic database snapshots."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from threading import Barrier, Event
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.services.skill_gaps import runs
from app.services.skill_gaps.runs import SkillGapRunManager
from app.services.skill_gaps.storage import save_json
from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, absent_response, reviewed_resume


def wait_for(manager, run):
    for _ in range(300):
        current = manager.get(run.id, user_id=run.user_id)
        if current.status in ("completed", "failed"):
            return current
        time.sleep(.01)
    raise AssertionError("Mock analysis did not finish")


class SkillGapRunOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.calls = []
        self.managers = []

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.temp.cleanup()

    def manager(self, invoker=None):
        def invoke(payload, save, on_request, timings):
            self.calls.append(deepcopy(payload))
            on_request()
            return absent_response(payload)
        manager = SkillGapRunManager(self.directory, invoker=invoker or invoke)
        self.managers.append(manager)
        return manager

    def submit(self, manager, **changes):
        data = dict(user_id=USER_ID, resume_id=RESUME_ID, reviewed_resume=reviewed_resume(),
                    filename="example.pdf", confirmed_at=CONFIRMED_AT, job_family="software_engineer")
        data.update(changes)
        return manager.submit(**data)

    def test_identical_run_reused_and_polling_latest_do_not_call_agent(self):
        manager = self.manager()
        first = wait_for(manager, self.submit(manager))
        self.assertEqual(first.status, "completed")
        self.assertEqual(first.model_calls, 1)
        self.assertEqual(self.submit(manager).id, first.id)
        self.assertTrue(self.submit(manager).reused)
        for _ in range(3):
            manager.get(first.id, user_id=USER_ID)
            latest = manager.latest(user_id=USER_ID, resume_id=RESUME_ID,
                reviewed_resume=reviewed_resume(), job_family="software_engineer")
            self.assertEqual(latest.id, first.id)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["resume_id"], str(RESUME_ID))
        self.assertEqual(first.report["resume_id"], str(RESUME_ID))
        self.assertEqual(first.report["user_id"], str(USER_ID))
        manifest = json.loads((self.directory / first.id / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["result_storage"], "local_json")
        self.assertEqual((manifest["repair_calls"], manifest["summary_calls"]), (0, 0))

    def test_force_creates_new_completed_run_but_never_duplicates_active_one(self):
        started, release = Event(), Event()
        def invoke(payload, save, on_request, timings):
            self.calls.append(payload)
            on_request()
            started.set()
            release.wait(5)
            return absent_response(payload)
        manager = self.manager(invoke)
        try:
            first = self.submit(manager)
            self.assertTrue(started.wait(2))
            self.assertEqual(self.submit(manager, force=True).id, first.id)
            self.assertEqual(len(self.calls), 1)
        finally:
            release.set()
        wait_for(manager, first)
        second = wait_for(manager, self.submit(manager, force=True))
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(second.model_calls, 1)

    def test_owner_and_resume_and_configuration_isolate_reuse_and_lookup(self):
        manager = self.manager()
        first = wait_for(manager, self.submit(manager))
        other = uuid4()
        with self.assertRaises(KeyError):
            manager.get(first.id, user_id=other)
        with self.assertRaises(KeyError):
            manager.latest(user_id=other, resume_id=RESUME_ID,
                reviewed_resume=reviewed_resume(), job_family="software_engineer")
        other_user = wait_for(manager, self.submit(manager, user_id=other))
        new_resume = wait_for(manager, self.submit(manager, resume_id=uuid4()))
        manager.fingerprint = "updated-test-configuration"
        with self.assertRaises(KeyError):
            manager.latest(user_id=USER_ID, resume_id=RESUME_ID,
                reviewed_resume=reviewed_resume(), job_family="software_engineer")
        configured = wait_for(manager, self.submit(manager))
        self.assertEqual(len({first.id, other_user.id, new_resume.id, configured.id}), 4)

    def test_recovery_does_not_retry_and_old_ownerless_records_stay_private(self):
        manager = self.manager()
        first = wait_for(manager, self.submit(manager))
        manager.close()
        state_path = self.directory / first.id / "status.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update(status="running", phase="agent", completed_at=None)
        save_json(state_path, state)
        legacy_id = uuid4().hex
        legacy = {**state, "id": legacy_id}
        legacy.pop("user_id")
        save_json(self.directory / legacy_id / "status.json", legacy)
        recovered = self.manager()
        result = recovered.get(first.id, user_id=USER_ID)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.model_calls, 1)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(KeyError):
            recovered.get(legacy_id, user_id=USER_ID)
        self.assertTrue((self.directory / legacy_id / "status.json").exists())

    def test_background_input_is_a_copy_of_database_snapshot(self):
        started, release = Event(), Event()
        def invoke(payload, save, on_request, timings):
            started.set()
            release.wait(5)
            self.calls.append(payload)
            on_request()
            return absent_response(payload)
        manager = self.manager(invoke)
        original = reviewed_resume()
        try:
            run = self.submit(manager, reviewed_resume=original)
            self.assertTrue(started.wait(2))
            original["technical_skills"].append("Changed after request")
        finally:
            release.set()
        self.assertEqual(wait_for(manager, run).status, "completed")
        saved = json.loads((self.directory / run.id / "reviewed_resume.json").read_text(encoding="utf-8"))
        self.assertNotIn("Changed after request", saved["reviewed_resume"]["technical_skills"])

    def test_queued_restart_is_failed_without_an_implicit_call(self):
        manager = self.manager()
        first = wait_for(manager, self.submit(manager))
        manager.close()
        state_path = self.directory / first.id / "status.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update(status="queued", phase="queued", completed_at=None, model_calls=0)
        save_json(state_path, state)
        recovered = self.manager()
        result = recovered.get(first.id, user_id=USER_ID)
        self.assertEqual((result.status, result.model_calls), ("failed", 0))
        self.assertEqual(len(self.calls), 1)

    def test_failed_submit_persist_leaves_no_stuck_run(self):
        manager = self.manager()
        first = wait_for(manager, self.submit(manager))
        with patch.object(manager, "_persist", side_effect=OSError("disk")), self.assertRaises(OSError):
            self.submit(manager, force=True)
        latest = manager.latest(user_id=USER_ID, resume_id=RESUME_ID,
            reviewed_resume=reviewed_resume(), job_family="software_engineer")
        self.assertEqual(latest.id, first.id)
        self.assertEqual(["completed"], [state["status"] for state in manager._states.values()])
        other = dict(reviewed_resume(), technical_skills=["Rust"])
        with patch.object(manager, "_persist", side_effect=OSError("disk")), self.assertRaises(OSError):
            self.submit(manager, reviewed_resume=other)
        self.assertEqual(wait_for(manager, self.submit(manager, reviewed_resume=other)).status, "completed")

    def test_failed_running_persist_ends_the_run_as_failed(self):
        manager = self.manager()
        persist = manager._persist
        def flaky(state):
            if state["phase"] == "preparing":
                raise OSError("disk")
            persist(state)
        with patch.object(manager, "_persist", side_effect=flaky):
            result = wait_for(manager, self.submit(manager))
        self.assertEqual((result.status, result.model_calls), ("failed", 0))
        self.assertEqual(self.calls, [])

    def test_concurrent_first_requests_construct_one_shared_manager(self):
        barrier = Barrier(6)
        sentinel = object()
        def construct():
            time.sleep(.05)  # Make simultaneous cold misses observable.
            return sentinel
        def request():
            barrier.wait(timeout=2)
            return runs.get_skill_gap_run_manager()
        runs._cached_skill_gap_run_manager.cache_clear()
        try:
            with patch.object(runs, "SkillGapRunManager", side_effect=construct) as constructor:
                with ThreadPoolExecutor(max_workers=6) as executor:
                    managers = list(executor.map(lambda _: request(), range(6)))
                constructor.assert_called_once_with()
                self.assertTrue(all(manager is sentinel for manager in managers))
        finally:
            runs._cached_skill_gap_run_manager.cache_clear()


if __name__ == "__main__":
    unittest.main()
