import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.services.plans import LocalPlanStore

FAMILY = "software_engineer"


class LocalPlanStorePositionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.store = LocalPlanStore(Path(self._directory.name))
        self.user = uuid4()

    def tearDown(self) -> None:
        self._directory.cleanup()

    def saved(self, resource_id: str) -> dict:
        return next(item for item in self.store.items(self.user, FAMILY) if item["resource_id"] == resource_id)

    def test_saving_without_a_position_stores_none(self) -> None:
        item = self.store.set_status(self.user, FAMILY, "swe_01", "saved")
        self.assertNotIn("position", item)
        self.assertIsNone(self.saved("swe_01").get("position"))

    def positions(self) -> dict[str, int | None]:
        return {item["resource_id"]: item.get("position") for item in self.store.items(self.user, FAMILY)}

    def test_a_suggested_plan_numbers_its_steps_in_order(self) -> None:
        self.store.save_suggested(self.user, FAMILY, ["swe_02", "swe_01"], ["club"])
        self.assertEqual(self.positions(), {"swe_02": 1, "swe_01": 2, "club": None})
        self.assertEqual({item["status"] for item in self.store.items(self.user, FAMILY)}, {"saved"})

    def test_a_new_suggested_plan_clears_the_old_positions(self) -> None:
        # Review on PR #58: plan A's X, Y must not stay ahead after plan B is added.
        self.store.save_suggested(self.user, FAMILY, ["x", "y"], [])
        self.store.set_status(self.user, FAMILY, "by_gap", "saved")
        self.store.save_suggested(self.user, FAMILY, ["z", "w"], [])
        self.assertEqual(self.positions(), {"x": None, "y": None, "by_gap": None, "z": 1, "w": 2})

    def test_a_suggested_plan_keeps_done_items_done(self) -> None:
        done = self.store.set_status(self.user, FAMILY, "swe_01", "done")
        self.store.save_suggested(self.user, FAMILY, ["swe_01", "swe_02"], [])
        item = self.saved("swe_01")
        self.assertEqual((item["status"], item["done_at"], item["position"]), ("done", done["done_at"], 1))

    def test_marking_done_keeps_the_position(self) -> None:
        self.store.save_suggested(self.user, FAMILY, ["swe_01"], [])
        self.store.set_status(self.user, FAMILY, "swe_01", "done")
        item = self.saved("swe_01")
        self.assertEqual((item["status"], item["position"]), ("done", 1))
        self.assertIsNotNone(item["done_at"])

if __name__ == "__main__":
    unittest.main()
