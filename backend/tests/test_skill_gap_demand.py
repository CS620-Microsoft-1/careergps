"""Offline demand replay tests using fictional postings, not local exports."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.demand_snapshot import (
    read_source, replay, snapshot_from_analysis, validate_source, verify_counts,
)


def fixture():
    parents = [
        {"job_posting_id": "se-1", "job_family": "software_engineer"},
        {"job_posting_id": "se-2", "job_family": "software_engineer"},
        {"job_posting_id": "se-empty", "job_family": "software_engineer"},
        {"job_posting_id": "da-1", "job_family": "data_analyst"},
        {"job_posting_id": "ai-1", "job_family": "ai_engineer"},
        {"job_posting_id": "unclassified", "job_family": None},
    ]
    qualifications = []
    for pid, text, level in [
        ("se-1", "Python programming", "required"),
        ("se-1", "Python programming", "required"),
        ("se-1", "Python programming", "preferred"),
        ("se-1", "SQL", "unspecified"),
        ("se-2", "Python programming", "preferred"),
        ("da-1", "SQL", "required"),
        ("ai-1", "Python programming", "unspecified"),
        ("unclassified", "Python programming", "required"),
    ]:
        qualifications.append({"job_posting_id": pid, "position": len(qualifications),
            "value": text, "level": level, "categories": [], "evidence": text})
    return parents, qualifications


class DemandReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parents, cls.qualifications = fixture()
        cls.analysis = replay(cls.parents, cls.qualifications)

    def family(self, name):
        return next(row for row in self.analysis["job_families"] if row["job_family"] == name)

    def test_posting_level_deduplication_and_level_precedence(self):
        family = self.family("software_engineer")
        skill = next(row for row in family["skills"] if row["skill_id"] == "programming")
        self.assertEqual(family["total_job_count"], 3)
        self.assertEqual(family["jobs_without_qualifications"], 1)
        self.assertEqual(skill["required_job_count"], 1)
        self.assertEqual(skill["preferred_only_job_count"], 1)
        self.assertEqual(skill["unspecified_job_count"], 0)
        self.assertEqual(skill["required_ratio"], 0.333333)
        self.assertEqual(skill["preferred_only_ratio"], 0.333333)
        self.assertEqual(skill["required_job_posting_ids"], ["se-1"])

    def test_unspecified_separate_and_null_family_excluded(self):
        self.assertEqual(self.analysis["quality"]["excluded_null_family_postings"], 1)
        self.assertEqual(self.analysis["quality"]["scoped_postings"], 5)
        se_sql = next(row for row in self.family("software_engineer")["skills"] if row["skill_id"] == "relational_sql")
        da_sql = next(row for row in self.family("data_analyst")["skills"] if row["skill_id"] == "sql")
        self.assertEqual(se_sql["unspecified_job_count"], 1)
        self.assertEqual(da_sql["required_job_count"], 1)
        self.assertEqual(da_sql["required_ratio"], 1)

    def test_replay_is_deterministic_except_timestamp(self):
        again = replay(self.parents, self.qualifications, batch_size=1)
        first = deepcopy(self.analysis)
        first.pop("generated_at")
        again.pop("generated_at")
        self.assertEqual(first, again)

    def test_export_does_not_recount_or_change_ratios(self):
        snapshot = snapshot_from_analysis(self.analysis, source_sha256="fixture-sha")
        self.assertFalse(snapshot["counts_recomputed"])
        self.assertEqual(snapshot["source_sha256"], "fixture-sha")
        verify_counts(self.analysis, snapshot)
        bad = deepcopy(snapshot)
        bad["families"]["software_engineer"]["skills"]["programming"]["required_job_count"] += 1
        with self.assertRaisesRegex(ValueError, "differ"):
            verify_counts(self.analysis, bad)

    def test_invalid_parent_and_foreign_key_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_source(self.parents + [self.parents[0]], self.qualifications)
        bad = deepcopy(self.qualifications)
        bad[0]["job_posting_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "reference"):
            validate_source(self.parents, bad)

    def test_zip_reader_uses_only_required_named_tables(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("tables/job_postings_analyses.json", json.dumps(self.parents))
                archive.writestr("tables/job_analysis_qualifications.json", json.dumps(self.qualifications))
                archive.writestr("tables/job_analysis_conditions.json", "[]")
            parents, qualifications, source = read_source(source_zip=path)
            self.assertEqual(parents, self.parents)
            self.assertEqual(qualifications, self.qualifications)
            self.assertEqual(source["source_kind"], "six_table_zip")

    def test_cli_writes_new_directory_and_never_overwrites(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            parents_path, qualifications_path = root / "parents.json", root / "qualifications.json"
            parents_path.write_text(json.dumps(self.parents), encoding="utf-8")
            qualifications_path.write_text(json.dumps(self.qualifications), encoding="utf-8")
            command = [sys.executable, "-m", "scripts.demand_snapshot", "replay", "--postings", str(parents_path),
                       "--qualifications", str(qualifications_path), "--output", str(root / "out"), "--batch-size", "1"]
            result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "out/software_engineer/batches/batch_0001.json").is_file())
            self.assertTrue((root / "out/demand_analysis.json").is_file())
            repeated = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)


if __name__ == "__main__":
    unittest.main()
