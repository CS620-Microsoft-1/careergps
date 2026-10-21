import copy
import json
import os
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# CI has no .env; creating the engine doesn't connect, so a dummy URL is enough.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test")

from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import Settings
from app.core.options import DEFAULT_UNIVERSITY
from app.core.security import AuthenticatedUser, SupabaseTokenVerifier
from app.main import app
from app.models import Resume, User
from app.schemas.me import AccountCreate, ResumeSubmit
from app.schemas.resume import ResumeClassification
from app.services import accounts
from tests.support import SUPABASE_URL, FakeJwks, make_token, new_signing_key

EXAMPLE = json.loads((BACKEND_ROOT.parent / "docs" / "resume-classification-example.json").read_text(encoding="utf-8"))


def classification(**personal) -> dict:
    data = copy.deepcopy(EXAMPLE)
    data["personal_information"].update(personal)
    return data


def resume_body(**changes) -> dict:
    body = {
        "original_filename": "ada.pdf",
        "parser": "pymupdf",
        "ocr_pages": [],
        "agent_name": "resume-classifier",
        "classification": classification(),
    }
    body.update(changes)
    return body


def onboarding_body(**changes) -> dict:
    body = {
        "accept_terms": True,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "target_role": "Data Analyst",
        "experience_level": "Internship",
        "graduation_year": datetime.now().year + 1,
        "preferred_location": "Madison, WI",
        "resume": resume_body(),
    }
    body.update(changes)
    return body


class FakeAccountService(accounts.AccountService):
    """In-memory stand-in for the database part of AccountService (the API tests need no database).

    It uses the same new_user / new_resume / fill_empty_contacts rules as the real service; the
    database rules themselves (foreign keys, CHECKs, cascades) are covered by test_accounts_postgres.
    """

    def __init__(self) -> None:
        super().__init__(db=None)  # type: ignore[arg-type]
        self.users: dict[uuid.UUID, User] = {}
        self.resumes: dict[uuid.UUID, Resume] = {}
        self.confirmed = True

    def get_user(self, user_id):
        return self.users.get(user_id)

    def email_is_confirmed(self, user_id):
        return self.confirmed

    def create_account(self, auth_user, data):
        if auth_user.id in self.users or any(
            user.primary_email == auth_user.email.lower() for user in self.users.values()
        ):
            raise accounts.AccountAlreadyExistsError
        if not self.email_is_confirmed(auth_user.id):
            raise accounts.EmailNotConfirmedError
        user = accounts.new_user(auth_user, data)
        user.created_at = datetime.now(UTC)
        self.users[user.id] = user
        resume = self._store(accounts.new_resume(user.id, data.resume))
        user.active_resume_id = resume.id
        return user

    def update_account(self, user, data):
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        return user

    def add_resume(self, user, data):
        resume = self._store(accounts.new_resume(user.id, data))
        user.active_resume_id = resume.id
        accounts.fill_empty_contacts(user, data.classification)
        return resume

    def get_active_resume(self, user):
        return self.resumes.get(user.active_resume_id)

    def sync_email(self, user, email):
        user.primary_email = email.lower()

    def _store(self, resume: Resume) -> Resume:
        resume.created_at = datetime.now(UTC)
        self.resumes[resume.id] = resume
        return resume


class NameAndContactRulesTests(unittest.TestCase):
    def test_new_user_takes_typed_names_and_contacts_and_university_from_the_resume(self) -> None:
        auth_user = AuthenticatedUser(id=uuid.uuid4(), email="Ada@Example.com")
        data = AccountCreate.model_validate(
            onboarding_body(
                first_name=" Ada ",
                last_name="King",
                resume=resume_body(classification=classification(name="Ada Lovelace", phones=["1", "1"])),
            )
        )

        user = accounts.new_user(auth_user, data)

        # Names as typed in onboarding; full_name is the résumé's, which may differ.
        self.assertEqual(("Ada", "King", "Ada Lovelace"), (user.first_name, user.last_name, user.full_name))
        self.assertEqual("ada@example.com", user.primary_email)
        self.assertEqual(EXAMPLE["education"][0]["institution"], user.university)
        self.assertEqual(["1"], user.phones)

    def test_university_falls_back_to_the_default(self) -> None:
        for education in ([], [{**EXAMPLE["education"][0], "institution": "  "}]):
            with self.subTest(education=education):
                data = ResumeClassification.model_validate({**classification(), "education": education})
                self.assertEqual(DEFAULT_UNIVERSITY, accounts.university_from(data))

    def test_a_newer_resume_fills_only_empty_contacts(self) -> None:
        user = User(phones=["111"], linkedin_url=None, resume_emails=[], github_url="gh-old", website_url=None)
        user.full_name = "Ada"
        user.current_location = None
        newer = ResumeClassification.model_validate(
            classification(phones=["222"], linkedin="li-new", emails=["new@example.com"], github="gh-new")
        )

        accounts.fill_empty_contacts(user, newer)

        self.assertEqual(["111"], user.phones)
        self.assertEqual("gh-old", user.github_url)
        self.assertEqual("li-new", user.linkedin_url)
        self.assertEqual(["new@example.com"], user.resume_emails)

    def test_contacts_fit_their_columns(self) -> None:
        long_url = "https://example.com/" + "a" * 2100
        data = ResumeClassification.model_validate(
            classification(location="x" * 300, linkedin=long_url, github=" https://github.com/ada ", name="n" * 300)
        )

        contacts = accounts.contact_details(data)

        self.assertEqual(255, len(contacts["current_location"]))
        self.assertEqual(255, len(contacts["full_name"]))
        self.assertIsNone(contacts["linkedin_url"])  # a cut URL wouldn't work, so it's dropped
        self.assertEqual("https://github.com/ada", contacts["github_url"])

    def test_resume_emails_are_lowercased_and_deduplicated(self) -> None:
        data = ResumeClassification.model_validate(
            classification(emails=["Ada@Example.com", "ada@example.com ", "", "grace@example.com"])
        )

        self.assertEqual(["ada@example.com", "grace@example.com"], accounts.contact_details(data)["resume_emails"])

    def test_new_resume_records_how_it_was_read(self) -> None:
        resume = accounts.new_resume(uuid.uuid4(), ResumeSubmit.model_validate(resume_body(original_filename="CV.DOCX")))

        self.assertEqual("docx", resume.file_type)
        self.assertEqual(accounts.RESUME_SCHEMA_VERSION, resume.schema_version)
        self.assertEqual(EXAMPLE, resume.confirmed_data)


class MeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = new_signing_key()
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(self.key))
        self.accounts = FakeAccountService()
        app.dependency_overrides[deps.get_account_service] = lambda: self.accounts
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        self.client = TestClient(app)

        self.user_id = uuid.uuid4()
        self.headers = self.auth_headers(self.user_id, "ada@example.com")

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def auth_headers(self, user_id: uuid.UUID, email: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(self.key, sub=str(user_id), email=email)}"}

    def onboard(self, headers=None, **changes):
        return self.client.post("/me", json=onboarding_body(**changes), headers=headers or self.headers)

    def test_onboarding_creates_the_account_and_first_resume(self) -> None:
        created = self.onboard()

        self.assertEqual(201, created.status_code, created.text)
        user = created.json()["user"]
        self.assertEqual(str(self.user_id), user["id"])
        self.assertEqual("ada@example.com", user["primary_email"])
        self.assertEqual("Data Analyst", user["target_role"])
        self.assertIsNotNone(user["active_resume_id"])

        resume = self.client.get("/me/resume", headers=self.headers)
        self.assertEqual(200, resume.status_code)
        self.assertEqual("ada.pdf", resume.json()["original_filename"])
        self.assertEqual(EXAMPLE, resume.json()["classification"])

    def test_me_is_empty_before_onboarding(self) -> None:
        response = self.client.get("/me", headers=self.headers)

        self.assertEqual(200, response.status_code)
        self.assertEqual({"user": None}, response.json())

    def test_second_onboarding_conflicts(self) -> None:
        self.onboard()

        self.assertEqual(409, self.onboard().status_code)

    def test_email_already_used_by_another_account_conflicts(self) -> None:
        self.onboard()

        response = self.onboard(headers=self.auth_headers(uuid.uuid4(), "ADA@example.com"))

        self.assertEqual(409, response.status_code)

    def test_unconfirmed_email_cannot_finish_onboarding(self) -> None:
        self.accounts.confirmed = False

        self.assertEqual(403, self.onboard().status_code)
        self.assertEqual({"user": None}, self.client.get("/me", headers=self.headers).json())

    def test_onboarding_validation(self) -> None:
        year = datetime.now().year
        cases = {
            "terms not accepted": onboarding_body(accept_terms=False),
            "unknown role": onboarding_body(target_role="Astronaut"),
            "unknown level": onboarding_body(experience_level="Part-time"),
            "year too early": onboarding_body(graduation_year=1999),
            "year too late": onboarding_body(graduation_year=year + 5),
            "blank location": onboarding_body(preferred_location=" "),
            "no first name": onboarding_body(first_name=" "),
            "no last name": {k: v for k, v in onboarding_body().items() if k != "last_name"},
            "first name too long": onboarding_body(first_name="A" * 101),
            "not a pdf or docx": onboarding_body(resume=resume_body(original_filename="ada.txt")),
            "malformed classification": onboarding_body(
                resume=resume_body(classification={**EXAMPLE, "unexpected": []})
            ),
            "email is taken from the token": onboarding_body(email="someone@else.com"),
            "university isn't asked yet": onboarding_body(university="MIT"),
        }
        for name, body in cases.items():
            with self.subTest(name):
                response = self.client.post("/me", json=body, headers=self.headers)
                self.assertEqual(422, response.status_code, response.text)

    def test_update_goals(self) -> None:
        self.onboard()

        response = self.client.patch(
            "/me",
            json={"preferred_location": "  Seattle, WA ", "target_role": "AI Engineer", "last_name": "King"},
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("Seattle, WA", response.json()["preferred_location"])
        self.assertEqual("AI Engineer", response.json()["target_role"])
        self.assertEqual("Internship", response.json()["experience_level"])
        self.assertEqual(("Ada", "King"), (response.json()["first_name"], response.json()["last_name"]))

    def test_update_validation(self) -> None:
        self.onboard()
        for body in ({"preferred_location": " "}, {"target_role": "Astronaut"}, {"first_name": " "}, {"university": "MIT"}):
            with self.subTest(body=body):
                self.assertEqual(422, self.client.patch("/me", json=body, headers=self.headers).status_code)

    def test_update_rejects_explicit_nulls(self) -> None:
        self.onboard()
        for field in ("first_name", "last_name", "target_role", "experience_level", "graduation_year", "preferred_location"):
            with self.subTest(field=field):
                response = self.client.patch("/me", json={field: None}, headers=self.headers)
                self.assertEqual(422, response.status_code, response.text)
        self.assertEqual("Ada", self.client.get("/me", headers=self.headers).json()["user"]["first_name"])

    def test_a_new_resume_becomes_active(self) -> None:
        self.onboard()

        added = self.client.post("/me/resumes", json=resume_body(original_filename="v2.docx"), headers=self.headers)

        self.assertEqual(201, added.status_code, added.text)
        self.assertEqual("docx", added.json()["file_type"])
        self.assertEqual("v2.docx", self.client.get("/me/resume", headers=self.headers).json()["original_filename"])
        self.assertEqual(2, len(self.accounts.resumes))

    def test_only_the_owner_sees_their_resume(self) -> None:
        self.onboard()
        other = self.auth_headers(uuid.uuid4(), "grace@example.com")
        self.onboard(headers=other, resume=resume_body(original_filename="grace.pdf"))

        self.assertEqual("ada.pdf", self.client.get("/me/resume", headers=self.headers).json()["original_filename"])
        self.assertEqual("grace.pdf", self.client.get("/me/resume", headers=other).json()["original_filename"])

    def test_login_email_is_synced(self) -> None:
        self.onboard()

        response = self.client.get("/me", headers=self.auth_headers(self.user_id, "Ada.New@example.com"))

        self.assertEqual("ada.new@example.com", response.json()["user"]["primary_email"])

    def test_needs_a_finished_onboarding(self) -> None:
        for method, path, body in (
            ("patch", "/me", {"target_role": "AI Engineer"}),
            ("get", "/me/resume", None),
            ("post", "/me/resumes", resume_body()),
        ):
            with self.subTest(path=path):
                response = self.client.request(method, path, json=body, headers=self.headers)
                self.assertEqual(403, response.status_code)

    def test_requires_a_valid_token(self) -> None:
        bad = {"Authorization": f"Bearer {make_token(new_signing_key())}"}
        for headers in ({}, bad):
            with self.subTest(headers=bool(headers)):
                for method, path in (
                    ("get", "/me"),
                    ("post", "/me"),
                    ("patch", "/me"),
                    ("get", "/me/resume"),
                    ("post", "/me/resumes"),
                ):
                    response = self.client.request(method, path, json={}, headers=headers)
                    self.assertEqual(401, response.status_code, f"{method} {path}")

    def test_auth_not_configured_returns_503(self) -> None:
        del app.dependency_overrides[deps.get_token_verifier]
        settings = Settings(_env_file=None, database_url="postgresql+psycopg://x:y@localhost/z")

        with mock.patch.object(deps, "get_settings", return_value=settings):
            response = self.client.get("/me", headers=self.headers)

        self.assertEqual(503, response.status_code)


if __name__ == "__main__":
    unittest.main()
