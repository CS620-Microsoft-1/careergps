import os
import sys
import unittest
import uuid
from datetime import date
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
    body = {
        "full_name": "Ada Student",
        "target_role": "AI Engineer",
        "graduation_year": date.today().year + 1,
        "university": "University of Wisconsin–Madison",
        "experience_level": "Internship",
        "accept_terms": True,
    }
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
        self.assertEqual("AI Engineer", body["profile"]["target_role"])
        self.assertIsNone(body["profile"]["location"])

        me = self.client.get("/me", headers=self.headers)
        self.assertEqual(200, me.status_code)
        self.assertEqual(body, me.json())

    def test_me_is_empty_before_sign_up_is_finished(self) -> None:
        response = self.client.get("/me", headers=self.headers)

        self.assertEqual(200, response.status_code)
        self.assertEqual({"user": None, "profile": None, "latest_resume": None}, response.json())

    def test_second_sign_up_conflicts(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)

        response = self.client.post("/me", json=valid_signup(), headers=self.headers)

        self.assertEqual(409, response.status_code)

    def test_email_already_used_by_another_account_conflicts(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        other = self.auth_headers(uuid.uuid4(), "ADA@example.com")

        response = self.client.post("/me", json=valid_signup(), headers=other)

        self.assertEqual(409, response.status_code)

    def test_requires_a_valid_token(self) -> None:
        bad = {"Authorization": f"Bearer {make_token(new_signing_key())}"}
        for headers in ({}, bad):
            with self.subTest(headers=bool(headers)):
                for method, path in (("get", "/me"), ("post", "/me"), ("patch", "/me/profile")):
                    response = self.client.request(method, path, json={}, headers=headers)
                    self.assertEqual(401, response.status_code, f"{method} {path}")

    def test_sign_up_validation(self) -> None:
        this_year = date.today().year
        cases = {
            "terms not accepted": valid_signup(accept_terms=False),
            "unknown role": valid_signup(target_role="Astronaut"),
            "unknown experience level": valid_signup(experience_level="Part-time"),
            "graduated already": valid_signup(graduation_year=this_year - 1),
            "too far ahead": valid_signup(graduation_year=this_year + 5),
            "blank name": valid_signup(full_name="   "),
            "name too long": valid_signup(full_name="x" * 101),
            "extra field": valid_signup(email="someone@else.com"),
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

    def test_update_rejects_goal_fields_and_blank_location(self) -> None:
        self.client.post("/me", json=valid_signup(), headers=self.headers)
        for body in ({"target_role": "Data Analyst"}, {"location": " "}):
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


class ProfilesMigrationTests(unittest.TestCase):
    def test_migration_enables_rls_and_links_users_to_supabase_auth(self) -> None:
        migration = next((BACKEND_ROOT / "migrations" / "versions").glob("*_add_profiles_*.py"))
        text = migration.read_text(encoding="utf-8")

        self.assertIn("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY", text)
        self.assertIn("referent_schema='auth'", text)


if __name__ == "__main__":
    unittest.main()
