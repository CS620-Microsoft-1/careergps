import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import SkillGapSettings
from app.schemas.skill_gap import ConfirmedResume, MarketInput
from app.services.skill_gap import calculate_gaps, mock_response, priority, validate_agent_result
from app.services.skill_gap_agent import SkillGapAgentError
from scripts.test_skill_gap_local import FIXTURES, run


def fixtures():
    return (
        ConfirmedResume.model_validate_json((FIXTURES / "confirmed_resume.json").read_text()),
        MarketInput.model_validate_json((FIXTURES / "market_profile.json").read_text()),
    )


class CalculationTests(unittest.TestCase):
    def test_scores_aliases_and_sort_order(self):
        resume, market = fixtures()
        inputs = calculate_gaps(resume, market)
        self.assertEqual(["Docker", "PostgreSQL", "Git", "JavaScript", "Python"],
                         [gap.skill for gap in inputs.calculated_gaps])
        self.assertEqual([0.8, 0.4875, 0.36, 0.28, 0.15],
                         [gap.gap_score for gap in inputs.calculated_gaps])
        self.assertEqual(0, inputs.calculated_gaps[0].user_evidence_score)

    def test_alias_duplicates_do_not_inflate_user_evidence(self):
        resume, market = fixtures()
        resume.candidate_skills.append(resume.candidate_skills[2].model_copy(
            update={"skill": "PostgreSQL", "evidence_score": 0.6}))
        inputs = calculate_gaps(resume, market)
        postgres = next(g for g in inputs.calculated_gaps if g.skill == "PostgreSQL")
        self.assertEqual(0.6, postgres.user_evidence_score)
        self.assertEqual(0.26, postgres.gap_score)

    def test_rejects_duplicate_market_aliases(self):
        resume, market = fixtures()
        market.skills.append(market.skills[2].model_copy(update={"skill": "Postgres"}))
        with self.assertRaisesRegex(ValueError, "Duplicate market skill"):
            calculate_gaps(resume, market)

    def test_empty_resume_means_no_evidence_not_no_ability(self):
        _, market = fixtures()
        inputs = calculate_gaps(ConfirmedResume(confirmed=True, candidate_skills=[]), market)
        self.assertTrue(all(g.gap_score == g.market_frequency for g in inputs.calculated_gaps))

    def test_empty_market_and_low_sample(self):
        resume, market = fixtures()
        market.skills = []
        market.sample_size = 0
        market.company_count = 0
        inputs = calculate_gaps(resume, market)
        self.assertEqual([], inputs.calculated_gaps)
        self.assertTrue(inputs.market.low_confidence)
        self.assertEqual([], validate_agent_result(mock_response(inputs), inputs).gaps)

    def test_priority_boundaries_and_full_evidence(self):
        self.assertEqual(["low", "medium", "medium", "high"],
                         [priority(x) for x in (0.299999, 0.3, 0.599999, 0.6)])
        resume, market = fixtures()
        resume.candidate_skills[0].evidence_score = 1
        inputs = calculate_gaps(resume, market)
        self.assertEqual(0, next(g for g in inputs.calculated_gaps if g.skill == "Python").gap_score)
        result = validate_agent_result(mock_response(inputs), inputs)
        python = next(g for g in result.gaps if g.skill == "Python")
        self.assertIn("Maintain", python.recommended_action)

    def test_positive_scores_need_evidence_and_empty_skill_names_fail(self):
        resume, market = fixtures()
        data = resume.model_dump()
        data["candidate_skills"][0]["evidence"] = []
        with self.assertRaises(ValidationError):
            ConfirmedResume.model_validate(data)
        resume.candidate_skills[0].skill = "   "
        with self.assertRaisesRegex(ValueError, "blank"):
            calculate_gaps(resume, market)

    def test_explicit_or_sparse_sample_confidence_is_propagated(self):
        resume, market = fixtures()
        for changes in ({"low_confidence": True}, {"sample_size": 29},
                        {"company_count": 2}, {"skills": []}):
            with self.subTest(changes=changes):
                inputs = calculate_gaps(resume, market.model_copy(update=changes))
                self.assertTrue(inputs.market.low_confidence)
                self.assertEqual("low", validate_agent_result(mock_response(inputs), inputs).confidence)

    def test_rejects_invalid_scores_and_unconfirmed_input(self):
        resume, market = fixtures()
        data = resume.model_dump()
        for value in (-0.1, 1.1, float("nan")):
            data["candidate_skills"][0]["evidence_score"] = value
            with self.assertRaises(ValidationError):
                ConfirmedResume.model_validate(data)
        data = resume.model_dump()
        data["confirmed"] = False
        with self.assertRaises(ValidationError):
            ConfirmedResume.model_validate(data)
        data = market.model_dump()
        data.update(sample_size=0, company_count=0)
        with self.assertRaises(ValidationError):
            MarketInput.model_validate(data)


class AgentValidationTests(unittest.TestCase):
    def setUp(self):
        self.inputs = calculate_gaps(*fixtures())
        self.payload = json.loads(mock_response(self.inputs))

    def test_mock_obeys_contract(self):
        result = validate_agent_result(json.dumps(self.payload), self.inputs)
        self.assertEqual(5, len(result.gaps))

    def test_rejects_numeric_changes(self):
        for field in ("gap_score", "market_frequency", "user_evidence_score"):
            with self.subTest(field=field):
                payload = json.loads(mock_response(self.inputs))
                payload["gaps"][0][field] = 0.5
                with self.assertRaises(ValueError):
                    validate_agent_result(json.dumps(payload), self.inputs)

    def test_rejects_missing_reordered_invented_and_wrong_priority(self):
        mutations = [
            lambda p: p["gaps"].pop(),
            lambda p: p["gaps"].reverse(),
            lambda p: p["gaps"][0].update(skill="Invented skill"),
            lambda p: p["gaps"][0].update(priority="low"),
            lambda p: p["strengths"].append({"skill": "Docker", "explanation": "Invented"}),
            lambda p: p.update(target_role="Other role"),
        ]
        for mutate in mutations:
            payload = json.loads(mock_response(self.inputs))
            mutate(payload)
            with self.assertRaises(ValueError):
                validate_agent_result(json.dumps(payload), self.inputs)

    def test_rejects_invalid_json_and_low_confidence_without_limitations(self):
        with self.assertRaises(ValueError):
            validate_agent_result("not json", self.inputs)
        self.inputs.market.low_confidence = True
        payload = json.loads(mock_response(self.inputs))
        payload["limitations"] = []
        with self.assertRaisesRegex(ValueError, "limitations"):
            validate_agent_result(json.dumps(payload), self.inputs)


class LocalRunnerTests(unittest.TestCase):
    def args(self, directory, mode="mock"):
        return argparse.Namespace(mode=mode, output_dir=Path(directory),
                                  resume=FIXTURES / "confirmed_resume.json",
                                  market=FIXTURES / "market_profile.json")

    def test_mock_writes_local_artifacts_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
                folder, passed = run(self.args(directory))
            self.assertTrue(passed)
            for name in ("confirmed_resume.json", "market_profile.json", "agent_input.json",
                         "raw_response.txt", "result.json", "report.md", "run.json", "prompt.md"):
                self.assertTrue((folder / name).exists(), name)
            self.assertFalse(json.loads((folder / "run.json").read_text())["database_used"])

    def test_rejected_agent_response_is_saved_but_not_published_as_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.test_skill_gap_local.call_foundry", return_value='{"bad":true}'):
                folder, passed = run(self.args(directory, "live"))
            self.assertFalse(passed)
            self.assertTrue((folder / "raw_response.txt").exists())
            self.assertTrue((folder / "error.json").exists())
            self.assertFalse((folder / "result.json").exists())

    def test_connection_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.test_skill_gap_local.call_foundry", side_effect=SkillGapAgentError("test failure")):
                folder, passed = run(self.args(directory, "live"))
            self.assertFalse(passed)
            self.assertEqual("failed", json.loads((folder / "run.json").read_text())["status"])

    def test_runner_never_imports_database_or_needs_database_url(self):
        # Separate interpreter catches accidental DB imports even when the full test suite imports SQLAlchemy.
        source = '''
import runpy, sys, tempfile
from pathlib import Path
sys.modules['sqlalchemy'] = None
sys.modules['psycopg'] = None
with tempfile.TemporaryDirectory() as directory:
    sys.argv = ['test_skill_gap_local', '--output-dir', directory]
    try:
        runpy.run_module('scripts.test_skill_gap_local', run_name='__main__')
    except SystemExit as result:
        assert result.code == 0, result.code
assert 'app.db.session' not in sys.modules
'''
        result = subprocess.run([sys.executable, "-c", source], cwd=FIXTURES.parents[2],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        settings = SkillGapSettings(_env_file=None)
        self.assertFalse(hasattr(settings, "database_url"))


if __name__ == "__main__":
    unittest.main()
