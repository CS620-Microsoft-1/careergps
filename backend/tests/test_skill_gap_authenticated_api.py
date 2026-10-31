"""Main-app integration tests: fake auth/accounts and Agent, no network or DB."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:placeholder@localhost:5432/test")

from fastapi.testclient import TestClient

from app.api import deps
from app.core.security import AuthenticatedUser, AuthError
from app.main import app
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, absent_response, reviewed_resume
from tests.test_skill_gap_run_ownership import wait_for


class FakeAccounts:
    def __init__(self):
        self.user = SimpleNamespace(id=USER_ID, target_role="Software Engineer")
        self.resume = SimpleNamespace(id=RESUME_ID, user_id=USER_ID, original_filename="saved-example.pdf",
            created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        # (user id, job family) -> résumé id: each destination has its own résumé.
        self.links = {(USER_ID, family): RESUME_ID for family in ("software_engineer", "data_analyst", "ai_engineer")}
        self.users = {USER_ID: self.user}
        self.resumes = {RESUME_ID: self.resume}

    def get_user(self, user_id):
        return self.users.get(user_id)

    def get_resume(self, user, job_family):
        return self.resumes.get(self.links.get((user.id, job_family)))

    def end_reads(self):
        pass


class FakeVerifier:
    def verify(self, token):
        try:
            return AuthenticatedUser(id=self.tokens[token], email="alex@example.invalid")
        except KeyError:
            raise AuthError("Invalid test token") from None

    def __init__(self, tokens):
        self.tokens = tokens


class AuthenticatedSkillGapApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        def invoke(payload, save, on_request, timings):
            self.calls.append(deepcopy(payload))
            on_request()
            return absent_response(payload)
        self.manager = SkillGapRunManager(Path(self.temp.name), invoker=invoke)
        self.accounts = FakeAccounts()
        self.other = uuid4()
        verifier = FakeVerifier({"owner-token": USER_ID, "other-token": self.other})
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        app.dependency_overrides[deps.get_account_service] = lambda: self.accounts
        app.dependency_overrides[get_skill_gap_run_manager] = lambda: self.manager
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer owner-token"}

    def tearDown(self):
        self.client.close()
        self.manager.close()
        app.dependency_overrides.clear()
        self.temp.cleanup()

    def test_all_skill_gap_endpoints_require_login_and_onboarding(self):
        paths = ("/skill-gaps/market/software_engineer", "/skill-gaps/runs/latest", "/skill-gaps/runs/" + "a" * 32)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post("/skill-gaps/runs", json={}).status_code, 401)
        other_headers = {"Authorization": "Bearer other-token"}
        self.assertEqual(self.client.post("/skill-gaps/runs", json={}, headers=other_headers).status_code, 403)
        self.assertEqual(self.calls, [])

    def test_start_reads_saved_resume_and_role_and_returns_real_identifiers(self):
        self.accounts.user.target_role = "Data Analyst"
        response = self.client.post("/skill-gaps/runs", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        run = self.manager.get(response.json()["id"], user_id=USER_ID)
        result = wait_for(self.manager, run)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.job_family, "data_analyst")
        self.assertEqual(str(result.resume_id), str(RESUME_ID))
        self.assertEqual(str(result.user_id), str(USER_ID))
        self.assertEqual(self.calls[0]["resume_id"], str(RESUME_ID))
        self.assertEqual(result.filename, "saved-example.pdf")
        self.assertEqual(len(self.calls), 1)

    def test_browser_cannot_override_resume_owner_confirmation_or_scores(self):
        for field in ("reviewed_resume", "confirmed", "user_id", "resume_id", "demand", "score"):
            response = self.client.post("/skill-gaps/runs", json={field: "untrusted"}, headers=self.headers)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.calls, [])

    def test_missing_wrong_owner_or_invalid_saved_resume_never_starts_agent(self):
        self.accounts.resume.user_id = self.other
        self.assertEqual(self.client.post("/skill-gaps/runs", json={}, headers=self.headers).status_code, 404)
        self.accounts.resume.user_id = USER_ID
        self.accounts.resume.confirmed_data = {"invalid": True}
        self.assertEqual(self.client.post("/skill-gaps/runs", json={}, headers=self.headers).status_code, 409)
        self.accounts.links.clear()
        self.assertEqual(self.client.get("/skill-gaps/runs/latest", headers=self.headers).status_code, 404)
        self.assertEqual(self.calls, [])

    def test_each_role_is_analyzed_with_its_own_resume(self):
        analyst = uuid4()
        self.accounts.resumes[analyst] = SimpleNamespace(id=analyst, user_id=USER_ID, original_filename="analyst.pdf",
            created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        self.accounts.links[(USER_ID, "data_analyst")] = analyst
        response = self.client.post("/skill-gaps/runs", json={"job_family": "data_analyst"}, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        result = wait_for(self.manager, self.manager.get(response.json()["id"], user_id=USER_ID))
        self.assertEqual(str(result.resume_id), str(analyst))
        self.assertEqual(result.filename, "analyst.pdf")
        # The selected role (Software Engineer) still has its own résumé and no analysis.
        self.assertEqual(self.client.get("/skill-gaps/runs/latest", headers=self.headers).status_code, 404)

    def test_latest_restores_by_server_identity_and_hides_other_users(self):
        self.assertEqual(self.client.get("/skill-gaps/runs/latest", headers=self.headers).status_code, 404)
        response = self.client.post("/skill-gaps/runs", json={}, headers=self.headers)
        run = self.manager.get(response.json()["id"], user_id=USER_ID)
        wait_for(self.manager, run)
        restored = self.client.get("/skill-gaps/runs/latest?job_family=software_engineer", headers=self.headers)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["id"], run.id)
        # A different account with identical text must neither retrieve nor reuse this run.
        other_resume_id = uuid4()
        self.accounts.users[self.other] = SimpleNamespace(id=self.other, target_role="Software Engineer")
        self.accounts.links[(self.other, "software_engineer")] = other_resume_id
        self.accounts.resumes[other_resume_id] = SimpleNamespace(id=other_resume_id, user_id=self.other,
            original_filename="other.pdf", created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        headers = {"Authorization": "Bearer other-token"}
        self.assertEqual(self.client.get("/skill-gaps/runs/" + run.id, headers=headers).status_code, 404)
        self.assertEqual(self.client.get("/skill-gaps/runs/latest", headers=headers).status_code, 404)
        self.assertEqual(len(self.calls), 1)



class ReadTransactionTests(unittest.TestCase):
    """The résumé read ends its transaction, so a long Agent call after it doesn't pin a pooled connection."""

    def setUp(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.services.accounts import AccountService

        fake = FakeAccounts()

        class SqliteAccounts(AccountService):
            def get_resume(self, user, job_family):
                self.db.execute(text("SELECT 1"))  # autobegins, like the real query
                return fake.resume

        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        self.db = Session(engine)
        self.addCleanup(self.db.close)
        self.accounts, self.user = SqliteAccounts(self.db), fake.user

    def test_saved_resume_leaves_no_open_transaction(self):
        from app.api.routes.skill_gaps import _saved_resume

        saved = _saved_resume(self.user, self.accounts, "software_engineer")

        self.assertEqual(saved.resume_id, RESUME_ID)
        self.assertFalse(self.db.in_transaction())

    def test_project_agent_runs_outside_a_transaction(self):
        from unittest.mock import patch
        from app.api.routes import resources as routes

        run = SimpleNamespace(id="x", resume_id=RESUME_ID, status="completed", job_family="ai_engineer", report={
            "job_family": "ai_engineer", "priority_order": ["rag"], "skills": [{"skill_id": "rag",
            "skill_name": "Retrieval-augmented generation", "skill_gap": 0.5, "calculation_state": "scored"}]})
        in_transaction = []
        def agent(**inputs):
            in_transaction.append(self.db.in_transaction())
            return {"recommendations": []}
        with patch.object(routes, "get_settings", return_value=SimpleNamespace(resources_project_endpoint="x")), \
             patch.object(routes, "recommend_projects", side_effect=agent):
            routes.projects_from_skill_gap(routes.RunProjectRequest(run_id="x"), self.user, self.accounts,
                                           SimpleNamespace(get=lambda identifier, user_id: run))
        self.assertEqual([False], in_transaction)


if __name__ == "__main__":
    unittest.main()
