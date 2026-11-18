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

    def test_saving_with_a_position_stores_it(self) -> None:
        self.store.set_status(self.user, FAMILY, "swe_01", "saved", position=2)
        self.assertEqual(self.saved("swe_01")["position"], 2)

    def test_marking_done_keeps_the_position(self) -> None:
        self.store.set_status(self.user, FAMILY, "swe_01", "saved", position=1)
        self.store.set_status(self.user, FAMILY, "swe_01", "done")
        item = self.saved("swe_01")
        self.assertEqual((item["status"], item["position"]), ("done", 1))
        self.assertIsNotNone(item["done_at"])

    def test_a_new_position_replaces_the_old_one(self) -> None:
        self.store.set_status(self.user, FAMILY, "swe_01", "saved", position=1)
        self.store.set_status(self.user, FAMILY, "swe_01", "saved", position=3)
        self.assertEqual(self.saved("swe_01")["position"], 3)


if __name__ == "__main__":
    unittest.main()
