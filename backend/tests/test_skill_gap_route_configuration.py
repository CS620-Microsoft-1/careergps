"""Configuration errors cross the authenticated API boundary without SDK leaks."""
from types import SimpleNamespace
import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:placeholder@localhost:5432/test")

from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.services.certifications.recommender import get_certification_recommender
from app.services.skill_gaps.runs import get_skill_gap_run_manager
from app.services.skill_gaps.transport import SkillGapConfigurationError
from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, reviewed_resume


class ConfigurationRouteTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.error = None
        self.status = "completed"
        self.recommendations = 0
        self.user = SimpleNamespace(id=USER_ID, target_role="Software Engineer")
        saved = SimpleNamespace(id=RESUME_ID, user_id=USER_ID, original_filename="example.pdf",
            created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())

        def end_reads():
            self.events.append("reads-ended")

        def latest(**kwargs):
            self.assertTrue(self.events and self.events[-1] == "reads-ended")
            if self.error is not None:
                raise self.error
            return SimpleNamespace(id="a" * 32, status=self.status, model_calls=3,
                job_family="software_engineer", report={})

        def recommend(run):
            self.recommendations += 1
            return {"job_family": run.job_family, "skill_gap_run_id": run.id,
                "source": "rules", "generated_at": "2026-11-04T00:00:00+00:00",
                "recommendations": []}

        accounts = SimpleNamespace(get_resume=lambda user, family: saved, end_reads=end_reads)
        manager = SimpleNamespace(latest=latest, submit=latest)
        app.dependency_overrides[deps.get_current_db_user] = lambda: self.user
        app.dependency_overrides[deps.get_account_service] = lambda: accounts
        app.dependency_overrides[get_skill_gap_run_manager] = lambda: manager
        app.dependency_overrides[get_certification_recommender] = lambda: SimpleNamespace(recommend=recommend)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_configuration_failures_return_503_for_submit_latest_and_certifications(self):
        public = "The saved skill-group configuration is unavailable."
        self.error = SkillGapConfigurationError("systems_agent_unavailable", public)
        for method, path in [("post", "/skill-gaps/runs"), ("get", "/skill-gaps/runs/latest"),
                             ("post", "/certifications/recommendations")]:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **({"json": {}} if method == "post" else {}))
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json(), {"detail": public})
        self.assertEqual(self.recommendations, 0)
        self.assertEqual(self.events, ["reads-ended"] * 3)

    def test_missing_completed_analysis_still_returns_404(self):
        self.error = KeyError("No current analysis")
        response = self.client.post("/certifications/recommendations", json={})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.recommendations, 0)

    def test_queued_running_and_failed_analysis_still_return_409(self):
        for status in ("queued", "running", "failed"):
            with self.subTest(status=status):
                self.status = status
                response = self.client.post("/certifications/recommendations", json={})
                self.assertEqual(response.status_code, 409)
                self.assertIn("failed" if status == "failed" else "not finished", response.json()["detail"])
        self.assertEqual(self.recommendations, 0)

    def test_completed_three_call_analysis_can_feed_certifications(self):
        response = self.client.post("/certifications/recommendations", json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["skill_gap_run_id"], "a" * 32)
        self.assertEqual(self.recommendations, 1)


if __name__ == "__main__":
    unittest.main()
