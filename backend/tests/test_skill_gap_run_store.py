"""Run stores behind SkillGapRunManager (app/services/skill_gaps/run_store.py). Synthetic data, no database."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from app.services.skill_gaps.run_store import JsonRunStore, run_folder
from app.services.skill_gaps.storage import save_json
from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, group_manager, reviewed_resume
from tests.test_skill_gap_run_ownership import wait_for


def state(identifier: str, **changes) -> dict:
    value = {"id": identifier, "user_id": str(USER_ID), "resume_id": str(RESUME_ID), "status": "queued",
             "phase": "queued", "job_family": "software_engineer", "resume_hash": "a" * 64,
             "calculation_fingerprint": "b" * 64, "model_calls": 0, "created_at": "2026-11-13T12:00:00+00:00",
             "completed_at": None, "elapsed_seconds": 0.0}
    value.update(changes)
    return value


class JsonRunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.store = JsonRunStore(self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_32_hex_ids_name_a_run_folder(self):
        identifier = uuid4().hex
        self.assertEqual(self.directory / identifier, run_folder(self.directory, identifier))
        for bad in ("../escape", identifier.upper(), identifier[:-1], str(uuid4())):
            with self.subTest(identifier=bad), self.assertRaises(KeyError):
                run_folder(self.directory, bad)

    def test_saved_states_load_back_with_a_readable_manifest(self):
        identifier = uuid4().hex
        self.store.save_state(state(identifier))
        self.assertEqual([state(identifier)], list(self.store.load_states()))
        manifest = json.loads((self.directory / identifier / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(("local_json", "queued", 0), (manifest["result_storage"], manifest["status"], manifest["repair_calls"]))

    def test_unreadable_or_misplaced_states_are_skipped(self):
        good, other = uuid4().hex, uuid4().hex
        self.store.save_state(state(good))
        save_json(self.directory / other / "status.json", state(uuid4().hex))  # id differs from its folder
        (self.directory / uuid4().hex).mkdir()  # a run folder without a state file
        broken = self.directory / uuid4().hex
        broken.mkdir()
        (broken / "status.json").write_text("{not json", encoding="utf-8")
        save_json(self.directory / "not-a-run" / "status.json", state("not-a-run"))
        self.assertEqual([good], [value["id"] for value in self.store.load_states()])

    def test_report_is_read_from_the_run_folder(self):
        identifier = uuid4().hex
        save_json(self.directory / identifier / "skill_gaps.json", {"job_family": "software_engineer"})
        self.assertEqual({"job_family": "software_engineer"}, self.store.load_report(identifier))


class RecordingStore(JsonRunStore):
    """Counts what the manager hands to its store."""

    def __init__(self, directory):
        super().__init__(directory)
        self.saved, self.reports, self.loads = [], [], 0

    def save_state(self, value):
        self.saved.append((value["id"], value["status"]))
        super().save_state(value)

    def load_states(self):
        self.loads += 1
        return super().load_states()

    def load_report(self, identifier):
        self.reports.append(identifier)
        return super().load_report(identifier)


class ManagerUsesItsStoreTests(unittest.TestCase):
    def test_state_recovery_and_reports_go_through_the_injected_store(self):
        with TemporaryDirectory() as directory:
            store = RecordingStore(Path(directory))
            manager = group_manager(Path(directory), store=store)
            try:
                self.assertEqual(1, store.loads)  # recovery at start-up
                run = wait_for(manager, manager.submit(
                    user_id=USER_ID, resume_id=RESUME_ID, reviewed_resume=reviewed_resume(),
                    filename="alex-example.pdf", confirmed_at=CONFIRMED_AT, job_family="software_engineer"))
            finally:
                manager.close()
        self.assertEqual("completed", run.status, run.error)
        statuses = [status for identifier, status in store.saved if identifier == run.id]
        self.assertEqual(("queued", "completed"), (statuses[0], statuses[-1]))
        self.assertIn("running", statuses)
        self.assertIn(run.id, store.reports)
        self.assertIsNotNone(run.report)


if __name__ == "__main__":
    unittest.main()
