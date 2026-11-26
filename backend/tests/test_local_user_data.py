"""Deleting one user's local result files (account deletion). Temp folders only; no DB or network."""
from pathlib import Path
import tempfile
import unittest
import uuid

from app.services.local_user_data import LocalDeletionReport, delete_local_user_data
from app.services.plans import LocalPlanStore
from app.services.skill_gaps.branch_cache import BranchCache
from app.services.skill_gaps.entry_level_cache import EntryLevelBranchCache
from app.services.skill_gaps.run_store import delete_run_folders


def _write(path: Path, text: str = "{}") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class LocalUserDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()
        self.addCleanup(self._temp.cleanup)

    def _seed(self, user: uuid.UUID, run: str) -> list[Path]:
        """Every kind of local file a user can have, with one skill-gap run."""
        LocalPlanStore(self.root / "plans").set_status(user, "software_engineer", "res-1", "saved")
        cache_dir = self.root / "web_skill_gaps" / "_branch_cache"
        return [
            self.root / "plans" / f"{user}.json",
            _write(self.root / "web_skill_gaps" / run / "status.json"),
            _write(BranchCache(cache_dir).owner_folder(str(user)) / "entry.json"),
            _write(EntryLevelBranchCache(cache_dir).owner_folder(str(user)) / "entry.json"),
            _write(self.root / "project_recommendations" / f"{run}.json"),
            _write(self.root / "certifications" / f"{run}.json"),
            _write(self.root / "action_plans" / run / "plan.json"),
        ]

    def test_removes_every_file_of_the_user_and_keeps_other_users(self) -> None:
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        run_a, run_b = uuid.uuid4().hex, uuid.uuid4().hex
        files_a, files_b = self._seed(user_a, run_a), self._seed(user_b, run_b)
        for path in files_a + files_b:
            self.assertTrue(path.exists(), path)

        report = delete_local_user_data(user_a, [run_a], root=self.root)

        self.assertEqual(LocalDeletionReport(plan_files=1, run_folders=1, branch_cache_folders=2, run_files=3),
                         report)
        for path in files_a:
            self.assertFalse(path.exists(), path)
        for path in files_b:
            self.assertTrue(path.exists(), path)

    def test_accepts_dashed_run_ids(self) -> None:
        user, run = uuid.uuid4(), uuid.uuid4()
        folder = _write(self.root / "web_skill_gaps" / run.hex / "status.json").parent
        delete_local_user_data(str(user), [str(run)], root=self.root)
        self.assertFalse(folder.exists())

    def test_nothing_to_delete_is_not_an_error(self) -> None:
        report = delete_local_user_data(uuid.uuid4(), [uuid.uuid4().hex], root=self.root)
        self.assertEqual(LocalDeletionReport(), report)

    def test_invalid_ids_remove_nothing(self) -> None:
        user, run = uuid.uuid4(), uuid.uuid4().hex
        files = self._seed(user, run)
        with self.assertRaises(ValueError):
            delete_local_user_data(user, [run, "../plans"], root=self.root)
        with self.assertRaises(ValueError):
            delete_local_user_data("../../etc", [run], root=self.root)
        for path in files:
            self.assertTrue(path.exists(), path)


class StoreDeleteMethodTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()
        self.addCleanup(self._temp.cleanup)

    def test_plan_store_delete_user(self) -> None:
        store, user = LocalPlanStore(self.root), uuid.uuid4()
        store.set_status(user, "data_analyst", "res-1", "done")
        self.assertTrue(store.delete_user(user))
        self.assertEqual([], store.items(user, "data_analyst"))
        self.assertFalse(store.delete_user(user))

    def test_run_folders_reject_non_run_ids_before_deleting(self) -> None:
        run = uuid.uuid4().hex
        folder = _write(self.root / run / "status.json").parent
        with self.assertRaises(KeyError):
            delete_run_folders(self.root, [run, ".."])
        self.assertTrue(folder.exists())
        self.assertEqual(1, delete_run_folders(self.root, [run]))
        self.assertEqual(0, delete_run_folders(self.root, [run]))

    def test_cache_owner_folders_match_where_entries_are_written(self) -> None:
        # owner_folder must be the parent _path() uses, or delete_owner would miss the entries.
        owner = str(uuid.uuid4())
        for cache in (BranchCache(self.root), EntryLevelBranchCache(self.root)):
            entry = cache._path({"owner": owner}, "key")
            self.assertEqual(cache.owner_folder(owner), entry.parent)
            _write(entry)
            self.assertTrue(cache.delete_owner(owner))
            self.assertFalse(entry.exists())
            self.assertFalse(cache.delete_owner(owner))


if __name__ == "__main__":
    unittest.main()
