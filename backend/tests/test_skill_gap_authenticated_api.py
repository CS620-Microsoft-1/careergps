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
        self.user = SimpleNamespace(id=USER_ID, active_resume_id=RESUME_ID, target_role="Software Engineer")
        self.resume = SimpleNamespace(id=RESUME_ID, user_id=USER_ID, original_filename="saved-example.pdf",
            created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        self.users = {USER_ID: self.user}
        self.resumes = {RESUME_ID: self.resume}

    def get_user(self, user_id):
        return self.users.get(user_id)

    def get_active_resume(self, user):
        return self.resumes.get(user.active_resume_id)


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
        self.accounts.user.active_resume_id = None
        self.assertEqual(self.client.get("/skill-gaps/runs/latest", headers=self.headers).status_code, 404)
        self.assertEqual(self.calls, [])

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
        self.accounts.users[self.other] = SimpleNamespace(id=self.other, active_resume_id=other_resume_id,
            target_role="Software Engineer")
        self.accounts.resumes[other_resume_id] = SimpleNamespace(id=other_resume_id, user_id=self.other,
            original_filename="other.pdf", created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        headers = {"Authorization": "Bearer other-token"}
        self.assertEqual(self.client.get("/skill-gaps/runs/" + run.id, headers=headers).status_code, 404)
        self.assertEqual(self.client.get("/skill-gaps/runs/latest", headers=headers).status_code, 404)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
