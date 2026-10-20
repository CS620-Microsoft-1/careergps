import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# CI has no .env; creating the engine doesn't connect, so a dummy URL is enough.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.core.config import Settings
from app.core.security import SupabaseTokenVerifier
from app.db.base import Base
from app.main import app
from app.services import accounts
from tests.support import SUPABASE_URL, FakeJwks, make_token, new_signing_key

# The API tests run on in-memory SQLite so CI needs no database. The models use only
# portable column types; Postgres-specific parts (RLS, the auth.users key) live in migrations.
engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def valid_signup(**changes) -> dict:
    body = {"accept_terms": True}
    body.update(changes)
    return body


class MeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

        self.key = new_signing_key()
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(self.key))
        app.dependency_overrides[deps.get_db] = override_get_db
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        self.client = TestClient(app)
        # SQLite has no auth schema; every Supabase account counts as confirmed unless a test says otherwise.
        confirmed = mock.patch.object(accounts, "email_is_confirmed", return_value=True)
        self.email_is_confirmed = confirmed.start()
        self.addCleanup(confirmed.stop)

        self.user_id = uuid.uuid4()
        self.headers = self.auth_headers(self.user_id, "ada@example.com")

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def auth_headers(self, user_id: uuid.UUID, email: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(self.key, sub=str(user_id), email=email)}"}

    def test_sign_up_then_read_me(self) -> None:
        created = self.client.post("/me", json=valid_signup(), headers=self.headers)

        self.assertEqual(201, created.status_code, created.text)
        body = created.json()
        self.assertEqual(str(self.user_id), body["user"]["id"])
        self.assertEqual("ada@example.com", body["user"]["email"])
        self.assertIsNone(body["user"]["full_name"])
        # Goal fields are asked in onboarding, so they start empty.
        for field in ("target_role", "graduation_year", "experience_level", "university", "location"):
            self.assertIsNone(body["profile"][field], field)

        me = self.client.get("/me", headers=self.headers)
        self.assertEqual(200, me.status_code)
        self.assertEqual(body, me.json())

    def test_me_is_empty_before_sign_up_is_finished(self) -> None:
        response = self.client.get("/me", headers=self.headers)

        self.assertEqual(200, response.status_code)
        self.assertEqual({"user": None, "profile": None}, response.json())

    def test_second_sign_up_conflicts(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)

        response = self.client.post("/me", json=valid_signup(), headers=self.headers)

        self.assertEqual(409, response.status_code)

    def test_email_already_used_by_another_account_conflicts(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        other = self.auth_headers(uuid.uuid4(), "ADA@example.com")

        response = self.client.post("/me", json=valid_signup(), headers=other)

        self.assertEqual(409, response.status_code)

    def test_unconfirmed_email_cannot_finish_sign_up(self) -> None:
        self.email_is_confirmed.return_value = False

        response = self.client.post("/me", json=valid_signup(), headers=self.headers)

        self.assertEqual(403, response.status_code)
        self.assertEqual({"user": None, "profile": None}, self.client.get("/me", headers=self.headers).json())

    def test_requires_a_valid_token(self) -> None:
        bad = {"Authorization": f"Bearer {make_token(new_signing_key())}"}
        for headers in ({}, bad):
            with self.subTest(headers=bool(headers)):
                for method, path in (("get", "/me"), ("post", "/me"), ("patch", "/me/profile")):
                    response = self.client.request(method, path, json={}, headers=headers)
                    self.assertEqual(401, response.status_code, f"{method} {path}")

    def test_sign_up_validation(self) -> None:
        cases = {
            "terms not accepted": valid_signup(accept_terms=False),
            "terms missing": {},
            "email is taken from the token, not the body": valid_signup(email="someone@else.com"),
        }
        for name, body in cases.items():
            with self.subTest(name):
                response = self.client.post("/me", json=body, headers=self.headers)
                self.assertEqual(422, response.status_code, response.text)

    def test_update_location(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)

        response = self.client.patch(
            "/me/profile", json={"location": "  Seattle, WA "}, headers=self.headers
        )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("Seattle, WA", response.json()["location"])

    def test_onboarding_saves_goals_name_and_completion(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        body = {
            "full_name": " Ada Lovelace ",
            "target_role": "Data Analyst",
            "experience_level": "Internship",
            "graduation_year": 2027,
            "university": "University of Wisconsin–Madison",
            "location": "Madison, WI",
            "complete_onboarding": True,
        }

        response = self.client.patch("/me/profile", json=body, headers=self.headers)

        self.assertEqual(200, response.status_code, response.text)
        profile = response.json()
        self.assertEqual("Data Analyst", profile["target_role"])
        self.assertEqual(2027, profile["graduation_year"])
        self.assertIsNotNone(profile["onboarding_completed_at"])
        self.assertEqual("Ada Lovelace", self.client.get("/me", headers=self.headers).json()["user"]["full_name"])

    def test_completing_onboarding_again_keeps_the_first_time(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        first = self.client.patch("/me/profile", json={"complete_onboarding": True}, headers=self.headers)

        again = self.client.patch(
            "/me/profile", json={"complete_onboarding": True, "location": "Seattle, WA"}, headers=self.headers
        )

        self.assertEqual(first.json()["onboarding_completed_at"], again.json()["onboarding_completed_at"])
        self.assertEqual("Seattle, WA", again.json()["location"])

    def test_update_validation(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        cases = (
            {"location": " "},
            {"target_role": "Astronaut"},
            {"experience_level": "Part-time"},
            {"graduation_year": 1900},
            {"graduation_year": 3000},
            {"complete_onboarding": False},
            {"terms_accepted_at": "2026-01-01T00:00:00Z"},
        )
        for body in cases:
            with self.subTest(body=body):
                response = self.client.patch("/me/profile", json=body, headers=self.headers)
                self.assertEqual(422, response.status_code)

    def test_update_before_sign_up_is_forbidden(self) -> None:
        response = self.client.patch(
            "/me/profile", json={"location": "Madison, WI"}, headers=self.headers
        )

        self.assertEqual(403, response.status_code)

    def test_auth_not_configured_returns_503(self) -> None:
        del app.dependency_overrides[deps.get_token_verifier]
        settings = Settings(_env_file=None, database_url="postgresql+psycopg://x:y@localhost/z")

        with mock.patch.object(deps, "get_settings", return_value=settings):
            response = self.client.get("/me", headers=self.headers)

        self.assertEqual(503, response.status_code)


class ResumeProfileApiTests(unittest.TestCase):
    """PUT/GET /me/resume, with MeApiTests' setup (borrowed, so its tests don't run twice)."""

    tearDown = MeApiTests.tearDown
    auth_headers = MeApiTests.auth_headers

    def setUp(self) -> None:
        MeApiTests.setUp(self)
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        example = BACKEND_ROOT.parent / "docs" / "resume-classification-example.json"
        self.classification = json.loads(example.read_text(encoding="utf-8"))

    def test_save_then_read(self) -> None:
        saved = self.client.put(
            "/me/resume",
            json={"filename": "ada.pdf", "classification": self.classification},
            headers=self.headers,
        )

        self.assertEqual(200, saved.status_code, saved.text)
        read = self.client.get("/me/resume", headers=self.headers)
        self.assertEqual(200, read.status_code)
        self.assertEqual("ada.pdf", read.json()["filename"])
        self.assertEqual(self.classification, read.json()["classification"])

    def test_a_new_upload_replaces_the_old_one(self) -> None:
        body = {"filename": "old.pdf", "classification": self.classification}
        self.client.put("/me/resume", json=body, headers=self.headers)

        self.client.put("/me/resume", json={**body, "filename": "new.pdf"}, headers=self.headers)

        self.assertEqual("new.pdf", self.client.get("/me/resume", headers=self.headers).json()["filename"])

    def test_nothing_saved_is_404(self) -> None:
        self.assertEqual(404, self.client.get("/me/resume", headers=self.headers).status_code)

    def test_only_the_owner_sees_it(self) -> None:
        self.client.put(
            "/me/resume", json={"filename": "ada.pdf", "classification": self.classification}, headers=self.headers
        )
        other = self.auth_headers(uuid.uuid4(), "grace@example.com")
        self.client.post("/me", json=valid_signup(), headers=other)

        self.assertEqual(404, self.client.get("/me/resume", headers=other).status_code)

    def test_rejects_a_malformed_classification(self) -> None:
        broken = {**self.classification, "unexpected": []}

        response = self.client.put(
            "/me/resume", json={"filename": "ada.pdf", "classification": broken}, headers=self.headers
        )

        self.assertEqual(422, response.status_code)

    def test_requires_a_finished_sign_up(self) -> None:
        stranger = self.auth_headers(uuid.uuid4(), "new@example.com")
        for method in ("get", "put"):
            with self.subTest(method=method):
                body = {"filename": "x.pdf", "classification": self.classification}
                response = self.client.request(method, "/me/resume", json=body, headers=stranger)
                self.assertEqual(403, response.status_code)


class ProfilesMigrationTests(unittest.TestCase):
    def test_migration_enables_rls_and_links_users_to_supabase_auth(self) -> None:
        migration = next((BACKEND_ROOT / "migrations" / "versions").glob("*_add_profiles_*.py"))
        text = migration.read_text(encoding="utf-8")

        self.assertIn("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY", text)
        self.assertIn("referent_schema='auth'", text)


if __name__ == "__main__":
    unittest.main()
