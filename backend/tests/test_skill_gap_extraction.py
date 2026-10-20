import argparse
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.schemas.skill_gap import AgentInput
from app.schemas.skill_gap_extraction import (
    JobRequirementsExtraction, PostingSnapshot, ResumeEvidenceExtraction, ReviewedResume, TargetScope,
)
from app.services.skill_gap import mock_response
from app.services.skill_gap_extraction import (
    aggregate_market, score_resume, select_postings, skill_is_explicit,
)
from scripts.test_skill_gap_local import FIXTURES
from scripts.test_skill_gap_pipeline import run


def source_fixtures():
    return (
        ReviewedResume.model_validate_json((FIXTURES / "reviewed_resume.json").read_text()),
        PostingSnapshot.model_validate_json((FIXTURES / "job_descriptions.json").read_text()),
        TargetScope.model_validate_json((FIXTURES / "target_scope.json").read_text()),
    )


def fake_job_extraction(documents):
    """Test double only: classify known, deliberately simple fixture sentences."""
    skills = ["Python", "Docker", "Git", "PostgreSQL", "JavaScript", "React", "SQL", "Kubernetes"]
    output = []
    for document in documents:
        category, requirements = "context", []
        for line in document.posting.description_text.splitlines():
            if line == "Required qualifications":
                category = "required"
            elif line == "Preferred qualifications":
                category = "preferred"
            elif line == "Eligibility":
                category = "context"
            for skill in skills:
                if skill_is_explicit(skill, line):
                    label = "negated" if re.search(r"not required|does not require", line) else category
                    requirements.append({"skill": skill, "requirement": label, "quote": line})
        output.append({"posting_id": document.posting_id, "skills": requirements})
    return JobRequirementsExtraction.model_validate({"postings": output})


def fake_resume_extraction(resume, names):
    locations = {
        "Python": ("/projects/0/content/1", "validated"),
        "JavaScript": ("/projects/1/content/0", "applied"),
        "React": ("/projects/1/content/0", "applied"),
        "PostgreSQL": ("/technical_skills/3", "listed"),
        "Git": ("/work_experience/0/content/0", "applied"),
        "SQL": ("/education/0/content/0", "listed"),
    }
    from app.services.skill_gap_extraction import resolve_pointer
    source = resume.classification.model_dump()
    output = []
    for name in names:
        citations = []
        if name in locations:
            path, kind = locations[name]
            citations = [{"path": path, "quote": resolve_pointer(source, path), "kind": kind}]
        output.append({"skill": name, "citations": citations})
    return ResumeEvidenceExtraction.model_validate({"skills": output})


class ExtractionCalculationTests(unittest.TestCase):
    def setUp(self):
        self.resume, self.snapshot, self.scope = source_fixtures()
        self.documents, self.filters = select_postings(self.snapshot, self.scope)
        self.jobs = fake_job_extraction(self.documents)

    def test_fixtures_reuse_current_contracts_without_scores_or_frequencies(self):
        for name in ("reviewed_resume.json", "job_descriptions.json"):
            text = (FIXTURES / name).read_text()
            for forbidden in ('"evidence_score"', '"gap_score"', '"frequency"'):
                self.assertNotIn(forbidden, text)
        self.assertEqual(7, len(self.snapshot.postings))

    def test_filters_duplicate_and_senior_before_denominator(self):
        self.assertEqual(5, len(self.documents))
        self.assertEqual(1, sum(row["reason"] == "duplicate" for row in self.filters))
        self.assertEqual(1, sum(row["reason"] == "not_entry_level" for row in self.filters))

    def test_country_date_missing_text_and_unknown_seniority_are_explicit(self):
        for mutation, expected in (
            ({"country": None}, "country_not_matched_or_unknown"),
            ({"published_at": None}, "published_date_unknown"),
            ({"description_text": ""}, "empty_description"),
            ({"title": "Software Engineer"}, "seniority_not_explicit_in_title"),
        ):
            with self.subTest(mutation=mutation):
                snapshot = self.snapshot.model_copy(deep=True)
                snapshot.postings = snapshot.postings[:-1]
                snapshot.postings[0].posting = snapshot.postings[0].posting.model_copy(update=mutation)
                _, audit = select_postings(snapshot, self.scope)
                self.assertEqual(expected, audit[0]["reason"])

    def test_frequencies_are_computed_from_mentions_and_real_denominator(self):
        market, audit = aggregate_market(self.jobs, self.documents, self.scope)
        frequencies = {s.skill: s.frequency for s in market.skills}
        self.assertEqual({"Python": 1, "Git": 1, "Docker": 0.8, "JavaScript": 0.6,
                          "PostgreSQL": 0.4, "SQL": 0.4, "React": 0.2}, frequencies)
        self.assertEqual(5, market.sample_size)
        self.assertEqual(4, market.company_count)
        self.assertTrue(market.low_confidence)
        docker = next(s for s in audit if s["skill"] == "Docker")
        self.assertEqual((1, 3), (docker["required_postings"], docker["preferred_only_postings"]))
        self.assertNotIn("Kubernetes", frequencies)

    def test_repeated_required_and_preferred_count_only_once(self):
        duplicate = self.jobs.postings[0].skills[0].model_copy(update={"requirement": "preferred"})
        self.jobs.postings[0].skills.extend([duplicate, duplicate])
        _, audit = aggregate_market(self.jobs, self.documents, self.scope)
        python = next(s for s in audit if s["skill"] == "Python")
        self.assertEqual(5, python["postings"])
        self.assertEqual((4, 1), (python["required_postings"], python["preferred_only_postings"]))

    def test_invented_quotes_or_missing_postings_fail(self):
        changed = self.jobs.model_copy(deep=True)
        changed.postings[0].skills[0].quote = "An invented skill statement."
        with self.assertRaisesRegex(ValueError, "Unverifiable"):
            aggregate_market(changed, self.documents, self.scope)
        changed = self.jobs.model_copy(deep=True)
        changed.postings.pop()
        with self.assertRaisesRegex(ValueError, "every selected posting"):
            aggregate_market(changed, self.documents, self.scope)

    def test_resume_categories_map_to_python_scores(self):
        names = ["Python", "Git", "JavaScript", "React", "PostgreSQL", "SQL", "Docker"]
        extraction = fake_resume_extraction(self.resume, names)
        scored, audit = score_resume(extraction, self.resume, names)
        self.assertEqual({"Python": 0.8, "Git": 0.6, "JavaScript": 0.6, "React": 0.6,
                          "PostgreSQL": 0.25, "SQL": 0.25, "Docker": 0},
                         {s.skill: s.evidence_score for s in scored.candidate_skills})
        self.assertTrue(all("citations" in item for item in audit))

    def test_listed_skill_cannot_claim_project_evidence_or_wrong_quote(self):
        extraction = fake_resume_extraction(self.resume, ["PostgreSQL"])
        extraction.skills[0].citations[0].kind = "validated"
        with self.assertRaisesRegex(ValueError, "content field"):
            score_resume(extraction, self.resume, ["PostgreSQL"])
        extraction = fake_resume_extraction(self.resume, ["Python"])
        extraction.skills[0].citations[0].quote = "Wrote tests with Docker."
        with self.assertRaisesRegex(ValueError, "Unverifiable"):
            score_resume(extraction, self.resume, ["Python"])

    def test_repeated_citation_does_not_inflate_score(self):
        extraction = fake_resume_extraction(self.resume, ["Python"])
        extraction.skills[0].citations *= 3
        scored, _ = score_resume(extraction, self.resume, ["Python"])
        self.assertEqual(0.8, scored.candidate_skills[0].evidence_score)

    def test_validated_evidence_in_two_independent_entries_can_score_one(self):
        self.resume.classification.work_experience[0].content[1] = "Wrote and ran Python data validation tests."
        extraction = fake_resume_extraction(self.resume, ["Python"])
        extraction.skills[0].citations.append(extraction.skills[0].citations[0].model_copy(update={
            "path": "/work_experience/0/content/1", "quote": "Wrote and ran Python data validation tests.",
        }))
        scored, _ = score_resume(extraction, self.resume, ["Python"])
        self.assertEqual(1, scored.candidate_skills[0].evidence_score)

    def test_wrong_skill_and_invalid_pointer_are_rejected(self):
        extraction = fake_resume_extraction(self.resume, ["Python"])
        extraction.skills[0].citations[0].path = "/projects/-1/content/0"
        with self.assertRaisesRegex(ValueError, "path does not exist"):
            score_resume(extraction, self.resume, ["Python"])
        extraction = fake_resume_extraction(self.resume, ["PostgreSQL"])
        extraction.skills[0].skill = "SQL"
        with self.assertRaisesRegex(ValueError, "Unverifiable"):
            score_resume(extraction, self.resume, ["SQL"])

    def test_aliases_are_not_parent_skills(self):
        self.assertTrue(skill_is_explicit("PostgreSQL", "Postgres"))
        self.assertFalse(skill_is_explicit("SQL", "PostgreSQL"))
        self.assertFalse(skill_is_explicit("Git", "GitHub"))


class RawPipelineTests(unittest.TestCase):
    def setUp(self):
        self.resume, snapshot, scope = source_fixtures()
        self.documents, _ = select_postings(snapshot, scope)

    def args(self, output_dir):
        return argparse.Namespace(resume=FIXTURES / "reviewed_resume.json",
                                  postings=FIXTURES / "job_descriptions.json",
                                  scope=FIXTURES / "target_scope.json", output_dir=Path(output_dir))

    def agent(self, request, prompt, settings):
        self.assertIn("Task dispatcher", prompt)
        if request["task"] == "extract_job_requirements":
            return fake_job_extraction(self.documents).model_dump_json()
        if request["task"] == "extract_resume_evidence":
            self.assertNotIn("personal_information", request["input"]["reviewed_resume"])
            return fake_resume_extraction(self.resume, request["input"]["skills_to_check"]).model_dump_json()
        return mock_response(AgentInput.model_validate(request["input"]))

    def test_all_stages_save_grounded_intermediates_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
                folder, passed = run(self.args(directory), self.agent)
            self.assertTrue(passed)
            result = json.loads((folder / "result.json").read_text())
            self.assertEqual(("Docker", 0.8), (result["gaps"][0]["skill"], result["gaps"][0]["gap_score"]))
            for name in ("posting_filter_audit.json", "resume_evidence_audit.json",
                         "market_skill_counts.json", "report.md"):
                self.assertTrue((folder / name).exists())

    def test_bad_extraction_stops_without_fabricated_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, passed = run(self.args(directory), lambda *_: '{"postings":[]}')
            self.assertFalse(passed)
            self.assertFalse((folder / "result.json").exists())
            self.assertEqual("extract_job_requirements", json.loads((folder / "error.json").read_text())["stage"])

    def test_unconfirmed_resume_is_rejected_before_agent_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unconfirmed.json"
            payload = self.resume.model_dump()
            payload["confirmed"] = False
            path.write_text(json.dumps(payload))
            args = self.args(directory)
            args.resume = path
            with patch("scripts.test_skill_gap_pipeline.call_foundry") as client:
                _, passed = run(args)
            self.assertFalse(passed)
            client.assert_not_called()

    def test_modules_import_without_database_packages(self):
        source = '''
import sys
sys.modules['sqlalchemy'] = None
sys.modules['psycopg'] = None
import scripts.test_skill_gap_pipeline
assert 'app.db.session' not in sys.modules
'''
        result = subprocess.run([sys.executable, "-c", source], cwd=FIXTURES.parents[2],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
