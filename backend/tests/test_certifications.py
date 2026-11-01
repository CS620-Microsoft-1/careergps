"""Certification catalog checks, gap ranking, Agent filtering/caching and the API; no network."""
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:placeholder@localhost:5432/test")

from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.schemas.skill_gap_web import SkillGapRun
from app.services.certifications.catalog import CATALOG_PATH, load_catalog, validate_catalog
from app.services.certifications.ranking import rank, top_gaps
from app.services.certifications.recommender import CertificationRecommender, get_certification_recommender
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from tests.skill_gap_fixtures import USER_ID, absent_response
from tests.test_skill_gap_authenticated_api import FakeAccounts, FakeVerifier
from tests.test_skill_gap_run_ownership import wait_for

CORE = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))


def cert(identifier, skills, **extra):
    return {"id": identifier, "name": identifier.title(), "provider": "Example", "url": "https://example.invalid",
            "cost_usd": 100, "cost_note": "Exam fee", "level": "beginner", "skills": skills,
            "last_verified": "2026-10-26", **extra}


RAW = {"version": "test-1", "certifications": [
    cert("cloud-basics", {"software_engineer": ["cloud"]}),
    cert("cloud-and-containers", {"software_engineer": ["cloud", "containers"]}),
    cert("security-basics", {"software_engineer": ["security"]}),
    cert("sql-basics", {"software_engineer": ["relational_sql"], "data_analyst": ["sql"]}),
]}


def report(priorities):
    return {"skills": [{"skill_id": skill, "skill_name": skill, "skill_gap": 1.0 if value else 0.0,
                        "skill_gap_grade": "F", "priority": value} for skill, value in priorities.items()]}


def completed_run(priorities, identifier="a" * 32, family="software_engineer"):
    return SkillGapRun(id=identifier, user_id=USER_ID, resume_id=USER_ID, status="completed", phase="completed",
                       job_family=family, filename="r.pdf", resume_hash="h", created_at="2026-10-26T00:00:00+00:00",
                       completed_at="2026-10-26T00:00:01+00:00", elapsed_seconds=1.0, model_calls=1,
                       report=report(priorities), error=None)


class CatalogTests(unittest.TestCase):
    def test_rejects_unknown_skill_duplicate_id_and_empty_family(self):
        for bad in ([cert("x", {"software_engineer": ["sql"]})],  # sql is a data_analyst id
                    [cert("x", {"software_engineer": ["cloud"]})] * 2,
                    [cert("x", {})]):
            with self.assertRaises(ValueError):
                validate_catalog({"version": "v", "certifications": bad}, CORE)

    def test_missing_file_means_an_empty_catalog(self):
        self.assertEqual(load_catalog(Path("/nonexistent/certifications.json"))["certifications"], [])

    def test_repository_catalog_is_valid_when_present(self):
        if not CATALOG_PATH.exists():
            self.skipTest("certifications.json not added yet")
        catalog = load_catalog()
        self.assertTrue(catalog["certifications"])


class RankingTests(unittest.TestCase):
    def test_top_gaps_skips_unscored_and_closed_skills(self):
        gaps = top_gaps(report({"cloud": 0.9, "security": 0.2, "testing": None, "containers": 0.0}))
        self.assertEqual([gap["skill_id"] for gap in gaps], ["cloud", "security"])

    def test_greedy_cover_prefers_breadth_and_avoids_repeating_a_gap(self):
        catalog = validate_catalog(RAW, CORE)
        gaps = top_gaps(report({"cloud": 0.9, "containers": 0.5, "security": 0.3}))
        picks = rank(catalog["certifications"][:3], "software_engineer", gaps)
        self.assertEqual([pick.certification_id for pick in picks], ["cloud-and-containers", "security-basics"])


class RecommenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = validate_catalog(RAW, CORE)
        self.calls = []
        self.output = {"recommendations": []}
        self.configured = True

    def tearDown(self):
        self.temp.cleanup()

    def recommender(self):
        def invoke(payload):
            self.calls.append(payload)
            if isinstance(self.output, Exception):
                raise self.output
            return self.output
        return CertificationRecommender(Path(self.temp.name), catalog=self.catalog, invoker=invoke,
                                        configured=lambda: self.configured)

    def test_agent_picks_are_limited_to_catalog_and_gap_skills_then_cached(self):
        self.output = {"recommendations": [
            {"certification_id": "made-up", "skill_ids": ["cloud"], "reason": "x"},
            {"certification_id": "sql-basics", "skill_ids": ["relational_sql"], "reason": "not a gap"},
            {"certification_id": "cloud-basics", "skill_ids": ["cloud", "security"], "reason": " Covers cloud. "},
        ]}
        recommender = self.recommender()
        run = completed_run({"cloud": 0.9, "security": 0.4})
        result = recommender.recommend(run)
        self.assertEqual(result.source, "agent")
        self.assertEqual([(r.certification_id, r.skill_ids, r.reason) for r in result.recommendations],
                         [("cloud-basics", ["cloud"], "Covers cloud.")])
        self.assertEqual({item["certification_id"] for item in self.calls[0]["catalog"]},
                         {"cloud-basics", "cloud-and-containers", "security-basics", "sql-basics"})
        self.assertEqual(recommender.recommend(run), result)
        self.assertEqual(len(self.calls), 1)

    def test_unconfigured_or_failing_agent_falls_back_to_rules_without_caching(self):
        run = completed_run({"security": 0.4})
        self.configured = False
        result = self.recommender().recommend(run)
        self.assertEqual((result.source, result.recommendations[0].certification_id), ("rules", "security-basics"))
        self.assertIsNone(result.recommendations[0].reason)
        self.assertEqual(self.calls, [])
        self.configured, self.output = True, RuntimeError("boom")
        self.assertEqual(self.recommender().recommend(run).source, "rules")
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_unfinished_run_is_rejected(self):
        run = completed_run({"cloud": 0.9}).model_copy(update={"status": "running", "report": None})
        with self.assertRaises(ValueError):
            self.recommender().recommend(run)


class CertificationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.temp.name)
        self.runs = SkillGapRunManager(root / "runs", invoker=lambda payload, save, on_request, timings:
                                       (on_request(), absent_response(payload))[1])
        self.recommender = CertificationRecommender(root / "certs", catalog=validate_catalog(RAW, CORE),
                                                    invoker=lambda payload: {"recommendations": []},
                                                    configured=lambda: False)
        self.accounts = FakeAccounts()
        verifier = FakeVerifier({"owner-token": USER_ID})
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        app.dependency_overrides[deps.get_account_service] = lambda: self.accounts
        app.dependency_overrides[get_skill_gap_run_manager] = lambda: self.runs
        app.dependency_overrides[get_certification_recommender] = lambda: self.recommender
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer owner-token"}

    def tearDown(self):
        self.client.close()
        self.runs.close()
        app.dependency_overrides.clear()
        self.temp.cleanup()

    def test_endpoints_require_login(self):
        self.assertEqual(self.client.get("/certifications/catalog/data_analyst").status_code, 401)
        self.assertEqual(self.client.post("/certifications/recommendations", json={}).status_code, 401)

    def test_catalog_is_filtered_by_family(self):
        response = self.client.get("/certifications/catalog/data_analyst", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()["certifications"]], ["sql-basics"])

    def test_recommendations_need_a_completed_run_for_the_direction(self):
        response = self.client.post("/certifications/recommendations", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 404, response.text)
        started = self.client.post("/skill-gaps/runs", json={}, headers=self.headers).json()
        wait_for(self.runs, self.runs.get(started["id"], user_id=USER_ID))
        response = self.client.post("/certifications/recommendations",
                                    json={"job_family": "software_engineer"}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["skill_gap_run_id"], body["source"]), (started["id"], "rules"))

    def test_failed_run_asks_for_a_new_analysis(self):
        def fail(payload, save, on_request, timings):
            raise RuntimeError("down")
        self.runs.close()
        self.runs = SkillGapRunManager(self.root / "failed", invoker=fail)
        started = self.client.post("/skill-gaps/runs", json={}, headers=self.headers).json()
        wait_for(self.runs, self.runs.get(started["id"], user_id=USER_ID))
        response = self.client.post("/certifications/recommendations",
                                    json={"job_family": "software_engineer"}, headers=self.headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("failed", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
