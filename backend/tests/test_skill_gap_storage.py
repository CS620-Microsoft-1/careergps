import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.skill_gaps import storage
from app.services.skill_gaps.storage import load, save_json


class SaveJsonTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "picks.json"

    def test_overlapping_writers_of_one_path_both_succeed(self):
        replace = os.replace
        def second_writer_finishes_first(source, target):
            patcher.stop()
            save_json(self.path, {"writer": 2})
            replace(source, target)
        patcher = patch.object(storage.os, "replace", side_effect=second_writer_finishes_first)
        patcher.start()
        save_json(self.path, {"writer": 1})
        self.assertEqual({"writer": 1}, load(self.path))
        self.assertEqual(["picks.json"], [p.name for p in self.path.parent.iterdir()])

    def test_failed_write_leaves_no_temp_file(self):
        with patch.object(storage.os, "replace", side_effect=OSError("disk")), self.assertRaises(OSError):
            save_json(self.path, {"a": 1})
        self.assertEqual([], list(self.path.parent.iterdir()))
        save_json(self.path, {"a": "é"})
        self.assertEqual('{\n  "a": "é"\n}\n', self.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
