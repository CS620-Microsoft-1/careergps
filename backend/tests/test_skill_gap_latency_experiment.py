import csv
import json
from pathlib import Path
import tempfile
import unittest

from app.schemas.resume import ResumeClassification
from experiments.skill_gap_latency import run as runner
from experiments.skill_gap_latency import summarize


def fake_invoke(version="7", output_tokens=900):
    def invoke(payload, save, on_request, timings):
        save("observed_agent.json", {"name": "skill-gap", "version": version,
                                     "definition": {"model": "gpt-5-mini", "reasoning": {"effort": "medium"}}})
        on_request()
        timings.update(sdk_auth_configuration_seconds=1.0, conversation_create_seconds=0.5,
                       inference_seconds=10.0, conversation_delete_seconds=0.25)
        save("agent.raw.json", {"model": "gpt-5-mini", "reasoning": {"effort": "medium"}, "usage": {
            "input_tokens": 1000, "input_tokens_details": {"cached_tokens": 400},
            "output_tokens": output_tokens, "output_tokens_details": {"reasoning_tokens": 600}}})
        skills = [skill["skill_id"] for skill in payload["core_skills"]]
        return {"task": "extract_resume_evidence", "result": {
            "job_family": payload["job_family"],
            **{skill: ({"kind": "practice", "operation_id": "a001"} if index == 0 else {"kind": "absent"})
               for index, skill in enumerate(skills)}}}
    return invoke


def fake_score(family, output, catalog, market, sources):
    return {"reference_validation": {"global_errors": [], "skills": {"x": {"errors": ["bad quote"]}}}}


class FixtureTests(unittest.TestCase):
    def test_all_nine_fixtures_validate(self):
        names = sorted(path.stem for path in runner.FIXTURES.glob("*.json"))
        self.assertEqual(names, sorted(runner.RESUMES))
        for name in names:
            with self.subTest(name=name):
                ResumeClassification.model_validate(json.loads((runner.FIXTURES / f"{name}.json").read_text()))

    def test_fixture_contacts_are_fake(self):
        for path in runner.FIXTURES.glob("*.json"):
            personal = json.loads(path.read_text())["personal_information"]
            self.assertTrue(all(email.endswith("@example.test") for email in personal["emails"]), path.name)
            self.assertTrue(all(phone.startswith("(555)") for phone in personal["phones"]), path.name)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.results = self.root / "results.csv"
        self.runs = self.root / "runs"

    def tearDown(self):
        self.tmp.cleanup()

    def test_schedule_is_interleaved_by_round(self):
        self.assertEqual(runner.schedule(("a", "b"), 2), [("a", 1), ("b", 1), ("a", 2), ("b", 2)])

    def test_run_writes_files_and_csv_row(self):
        rows = runner.run("A", ("swe_strong",), 1, invoke=fake_invoke(), results=self.results,
                          runs_root=self.runs, score=fake_score, log=lambda _: None)
        row = rows[0]
        self.assertEqual(row["status"], "ok")
        self.assertEqual((row["calls"], row["agent_version"], row["reasoning_effort"]), (1, "7", "medium"))
        self.assertEqual((row["setup_s"], row["inference_s"], row["conversation_s"]), (1.0, 10.0, 0.75))
        self.assertEqual((row["input_tokens"], row["cached_tokens"], row["output_tokens"], row["reasoning_tokens"]),
                         (1000, 400, 900, 600))
        self.assertEqual((row["practice"], row["absent"], row["reference_errors"]), (1, 21, 1))
        folder = self.runs / row["run_dir"]
        for name in ("input.json", "observed_agent.json", "agent.raw.json", "agent.response.json",
                     "skill_gaps.json", "metrics.json"):
            self.assertTrue((folder / name).exists(), name)
        with self.results.open() as handle:
            written = list(csv.DictReader(handle))
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["resume"], "swe_strong")

    def test_failed_call_is_recorded_not_raised(self):
        def broken(payload, save, on_request, timings):
            on_request()
            raise RuntimeError("Agent response incomplete")
        rows = runner.run("A", ("da_weak",), 1, invoke=broken, results=self.results,
                          runs_root=self.runs, score=fake_score, log=lambda _: None)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertIn("Agent response incomplete", rows[0]["error"])
        self.assertIsNone(rows[0]["output_tokens"])

    def test_stops_when_agent_version_changes(self):
        versions = iter(["7", "8"])

        def invoke(*args):
            return fake_invoke(next(versions))(*args)
        with self.assertRaises(runner.AgentVersionChanged):
            runner.run("A", ("swe_strong", "swe_weak", "da_weak"), 1, invoke=invoke, results=self.results,
                       runs_root=self.runs, score=fake_score, log=lambda _: None)
        with self.results.open() as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 2)

    def test_max_calls_limits_plan(self):
        rows = runner.run("A", runner.RESUMES, 3, invoke=fake_invoke(), results=self.results,
                          runs_root=self.runs, score=fake_score, max_calls=2, log=lambda _: None)
        self.assertEqual([(row["resume"], row["round"]) for row in rows], [("swe_strong", 1), ("swe_medium", 1)])


class SummaryTests(unittest.TestCase):
    def row(self, resume, total, verdicts, status="ok", output="900"):
        role = runner.FAMILIES[resume.split("_")[0]]
        return {"config": "A", "resume": resume, "role": role, "level": resume.split("_")[1], "round": "1",
                "started_at": "2026-11-03T15:00:00+00:00", "status": status, "error": "" if status == "ok" else "boom",
                "agent_name": "skill-gap", "agent_version": "7", "model": "gpt-5-mini", "reasoning_effort": "medium",
                "total_s": str(total), "inference_s": str(total - 2), "output_tokens": output,
                "reference_errors": "0", "verdicts": json.dumps(verdicts)}

    def test_stats(self):
        result = summarize.stats([{"x": "1"}, {"x": "3"}, {"x": ""}, {"x": "8"}], "x")
        self.assertEqual((result["mean"], result["median"], result["min"], result["max"], result["n"]), (4, 3, 1, 8, 3))

    def test_agreement(self):
        rows = [self.row("swe_strong", 60, {"a": ["practice", "x1"], "b": ["absent", None]}),
                self.row("swe_strong", 61, {"a": ["practice", "x2"], "b": ["absent", None]}),
                self.row("swe_strong", 62, {"a": ["practice", "x1"], "b": ["knowledge", None]})]
        self.assertEqual(summarize.agreement(rows), (0.5, 0.0))
        self.assertEqual(summarize.agreement(rows[:1]), (None, None))

    def test_group_agreement_averages_per_resume(self):
        same = {"a": ["absent", None]}
        rows = [self.row("swe_strong", 60, same), self.row("swe_strong", 61, same),
                self.row("swe_weak", 30, {"a": ["knowledge", None]}), self.row("swe_weak", 31, same)]
        self.assertEqual(summarize.mean_agreement(rows), (0.5, 0.5))

    def test_report_keeps_text_outside_markers(self):
        rows = [self.row("swe_strong", 60, {"a": ["absent", None]}),
                self.row("swe_strong", 70, {"a": ["absent", None]}),
                self.row("da_weak", 40, {}, status="failed", output="")]
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "REPORT.md"
            report.write_text(f"intro\n{summarize.START}\nold\n{summarize.END}\nnotes\n")
            summarize.write_report(rows, report)
            text = report.read_text()
        self.assertTrue(text.startswith("intro\n") and text.endswith("notes\n"))
        self.assertNotIn("\nold\n", text)
        self.assertIn("| swe_strong | 2/2 | 65.0 | 60.0 | 70.0 |", text)
        self.assertIn("| B | Single Agent, low reasoning (1 call) | not run yet |", text)
        self.assertIn("- da_weak r1: boom", text)


if __name__ == "__main__":
    unittest.main()
