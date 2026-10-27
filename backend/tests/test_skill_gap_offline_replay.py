"""Portable offline replay tests with fictional inputs and no saved private runs."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.input import prepare
from app.services.skill_gaps.response import calculate_web_report
from scripts.replay_skill_gap_response import replay, source_hashes


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class OfflineReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.run = self.directory / "saved-run"
        self.run.mkdir()
        load = lambda name: json.loads((ASSET_ROOT / name).read_text(encoding="utf-8"))
        catalog, market = load("core_catalog.json"), load("market_snapshot.json")
        payload = prepare("software_engineer", {"technical_skills": ["Python"]},
                          "22222222-2222-4222-8222-222222222222", catalog)
        response = {"task": "extract_resume_evidence", "result": {
            "job_family": "software_engineer", **{
                skill["skill_id"]: {"kind": "absent"} for skill in payload["core_skills"]}}}
        report = calculate_web_report("software_engineer", response, catalog, market, payload["resume_sources"])
        report.update(user_id="11111111-1111-4111-8111-111111111111",
                      resume_id=payload["resume_id"], database_used=False)
        for name, value in {"input.json": payload, "agent.response.json": response,
                            "agent.raw.json": {"example": "fictional saved response"},
                            "skill_gaps.json": report, "status.json": {
                                "status": "completed", "id": "a" * 32, "model_calls": 1,
                                "elapsed_seconds": 3.5}}.items():
            save(self.run / name, value)

    def test_replay_is_offline_and_preserves_source_and_metadata(self):
        before = source_hashes(self.run)
        output = self.directory / "replay"
        with patch("socket.socket", side_effect=AssertionError("No network permitted")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("No network permitted")):
            result = replay(self.run, output)
        self.assertEqual(result["new_model_calls"], 0)
        self.assertEqual(result["original_model_calls"], 1)
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(result["changed_skill_ids"], [])
        self.assertEqual(result["changed_previously_scored_skill_ids"], [])
        self.assertEqual(len(result["unchanged_previously_scored_skill_ids"]), 22)
        self.assertEqual(source_hashes(self.run), before)
        self.assertTrue(result["source_files_unchanged"])
        report = json.loads((output / "skill_gaps.after.json").read_text(encoding="utf-8"))
        original = json.loads((self.run / "skill_gaps.json").read_text(encoding="utf-8"))
        for field in ("user_id", "resume_id", "database_used"):
            self.assertEqual(report[field], original[field])
        for filename in ("skill_gaps.before.json", "skill_gaps.after.json", "comparison.json",
                         "response_processing.json", "local_checks.json", "README.md"):
            self.assertTrue((output / filename).is_file(), filename)

    def test_existing_output_or_output_inside_source_is_refused(self):
        existing = self.directory / "existing"
        existing.mkdir()
        marker = existing / "marker.txt"
        marker.write_text("keep", encoding="utf-8")
        for output in (self.run, self.run / "child-replay", existing):
            with self.subTest(output=output), self.assertRaises(ValueError):
                replay(self.run, output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_changed_demand_or_policy_is_refused_before_output(self):
        path = self.run / "skill_gaps.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for field in ("demand", "policy"):
            value = json.loads(json.dumps(original))
            if field == "demand":
                value["skills"][0]["demand"]["required_job_count"] += 1
            else:
                value["policy_version"] = "incompatible-test-policy"
            save(path, value)
            output = self.directory / ("replay-" + field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay(self.run, output)
            self.assertFalse(output.exists())

    def test_running_source_is_refused(self):
        save(self.run / "status.json", {"status": "running"})
        with self.assertRaises(ValueError):
            replay(self.run, self.directory / "replay")

    def test_cli_works_without_private_configuration(self):
        output = self.directory / "cli-replay"
        process = subprocess.run([sys.executable, "-m", "scripts.replay_skill_gap_response",
            "--run-dir", str(self.run), "--output", str(output)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["new_model_calls"], 0)
        self.assertEqual(result["after"]["skill_count"], 22)
        self.assertTrue(result["source_files_unchanged"])


if __name__ == "__main__":
    unittest.main()
