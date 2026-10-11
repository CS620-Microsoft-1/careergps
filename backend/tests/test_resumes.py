import os
import sys
import unittest
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# CI has no .env; creating the engine doesn't connect, so a dummy URL is enough.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.core.config import Settings
from app.core.security import SupabaseTokenVerifier
from app.db.base import Base
from app.main import app
from app.models import Education, Experience, Profile, Project, Resume, Skill
from app.schemas.resume import ResumeExtraction
from app.services.llm import LLMInvalidOutputError, LLMUnavailableError
from app.services.storage import StorageError
from tests.support import (
    RESUME_LINES,
    SUPABASE_URL,
    FakeJwks,
    make_pdf,
    make_token,
    new_signing_key,
)

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.fail = False

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail:
            raise StorageError("down")
        self.files[key] = data

    def get(self, key: str) -> bytes:
        return self.files[key]

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


class FakeLLM:
    """Returns (or raises) the queued outcomes in order, and records the instructions it got."""

    name = "fake-model"

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    def extract(self, schema, instructions: str, content: str):
        self.calls.append(instructions)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def extraction() -> ResumeExtraction:
    return ResumeExtraction.model_validate(
        {
            "contact": {
                "full_name": "Ada Student",
                "email": "ada@example.com",
                "phone": "(608) 555-0100",
                "location": "Madison, WI",
                "links": ["https://github.com/ada"],
            },
            "education": [
                {
                    "school": "University of Wisconsin-Madison",
                    "degree": "B.S.",
                    "field_of_study": "Computer Science",
                    "start_date": "2023",
                    "end_date": "2027",
                    "gpa": "3.8",
                }
            ],
            "experience": [
                {
                    "company": "Example Corp",
                    "title": "Software Engineering Intern",
                    "location": "Seattle, WA",
                    "start_date": "2025-06",
                    "end_date": "2025-08",
                    "is_current": False,
                    "bullets": ["Built a FastAPI service", "Cut test runtime by 40 percent"],
                }
            ],
            "projects": [],
            "skills": [
                {"name": "Python", "category": "language"},
                {"name": "FastAPI", "category": "framework"},
            ],
        }
    )


class ResumeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

        self.key = new_signing_key()
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(self.key))
        self.storage = FakeStorage()
        self.llm = FakeLLM(extraction())
        app.dependency_overrides.update(
            {
                deps.get_db: override_get_db,
                deps.get_token_verifier: lambda: verifier,
                deps.get_storage: lambda: self.storage,
                deps.get_llm_client: lambda: self.llm,
                deps.get_session_factory: lambda: TestingSession,
            }
        )
        self.client = TestClient(app)
        self.user_id = uuid.uuid4()
        self.headers = self.sign_up(self.user_id, "ada@example.com")

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def sign_up(self, user_id: uuid.UUID, email: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {make_token(self.key, sub=str(user_id), email=email)}"}
        body = {
            "full_name": "Ada Student",
            "target_role": "AI Engineer",
            "graduation_year": date.today().year + 1,
            "university": "UW–Madison",
            "experience_level": "Internship",
            "accept_terms": True,
        }
        self.assertEqual(201, self.client.post("/me", json=body, headers=headers).status_code)
        return headers

    def upload(self, data: bytes | None = None, headers=None, filename="C:\\Users\\ada\\resume.pdf"):
        files = {"file": (filename, data or make_pdf([RESUME_LINES]), "application/pdf")}
        return self.client.post("/resumes", files=files, headers=headers or self.headers)

    def get(self, resume_id: str, headers=None):
        return self.client.get(f"/resumes/{resume_id}", headers=headers or self.headers)

    def set_resume(self, resume_id: str, **values) -> None:
        with TestingSession() as db:
            resume = db.get(Resume, uuid.UUID(resume_id))
            for name, value in values.items():
                setattr(resume, name, value)
            db.commit()

    # --- upload and parsing ------------------------------------------------------------------

    def test_upload_is_parsed_in_the_background(self) -> None:
        response = self.upload()

        self.assertEqual(202, response.status_code, response.text)
        body = response.json()
        self.assertEqual("pending", body["status"])
        self.assertEqual("resume.pdf", body["original_filename"])
        self.assertEqual([f"{self.user_id}/{body['id']}.pdf"], list(self.storage.files))

        parsed = self.get(body["id"]).json()
        self.assertEqual("parsed", parsed["status"])
        self.assertEqual("Ada Student", parsed["parsed_data"]["contact"]["full_name"])

        me = self.client.get("/me", headers=self.headers).json()
        self.assertEqual("parsed", me["latest_resume"]["status"])

    def test_llm_receives_pdf_links_and_resume_as_data(self) -> None:
        captured = {}

        def extract(schema, instructions, content):
            captured["content"] = content
            return extraction()

        self.llm.extract = extract
        self.upload(make_pdf([RESUME_LINES], link="https://github.com/ada"))

        self.assertIn("https://github.com/ada", captured["content"])
        self.assertIn("<resume>", captured["content"])

    def test_upload_rejects_bad_files(self) -> None:
        cases = {
            "not a pdf": (b"PK\x03\x04 this is a docx", 415),
            "damaged pdf": (b"%PDF-1.4 garbage", 422),
            "too many pages": (make_pdf([["page"]] * 11), 422),
            "too large": (b"%PDF-" + b"0" * (10 * 1024 * 1024), 413),
        }
        for name, (data, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(expected, self.upload(data).status_code)
        self.assertEqual({}, self.storage.files)

    def test_upload_requires_finished_sign_up(self) -> None:
        headers = {"Authorization": f"Bearer {make_token(self.key)}"}

        self.assertEqual(403, self.upload(headers=headers).status_code)

    def test_scanned_pdf_fails_with_no_text_and_can_be_replaced(self) -> None:
        first = self.upload(make_pdf([["Scanned page"]])).json()

        failed = self.get(first["id"]).json()
        self.assertEqual(("failed", "no_text"), (failed["status"], failed["error_code"]))
        self.assertEqual([], self.llm.calls)

        second = self.upload()
        self.assertEqual(202, second.status_code)
        self.assertEqual(404, self.get(first["id"]).status_code)
        self.assertEqual([f"{self.user_id}/{second.json()['id']}.pdf"], list(self.storage.files))

    def test_only_a_failed_resume_can_be_replaced(self) -> None:
        resume_id = self.upload().json()["id"]

        self.assertEqual(409, self.upload().status_code)
        self.set_resume(resume_id, status="confirmed")
        self.assertEqual(409, self.upload().status_code)

    def test_invalid_llm_output_is_retried_once_with_the_errors(self) -> None:
        self.llm.outcomes = [LLMInvalidOutputError("skills.0.category: bad value"), extraction()]

        resume_id = self.upload().json()["id"]

        self.assertEqual("parsed", self.get(resume_id).json()["status"])
        self.assertEqual(2, len(self.llm.calls))
        self.assertIn("skills.0.category: bad value", self.llm.calls[1])

    def test_llm_failures(self) -> None:
        cases = {
            "invalid twice": ([LLMInvalidOutputError("x"), LLMInvalidOutputError("y")], "llm_invalid_output"),
            "provider down": ([LLMUnavailableError("timeout")], "llm_unavailable"),
            "unexpected error": ([RuntimeError("boom")], "internal"),
        }
        for name, (outcomes, error_code) in cases.items():
            with self.subTest(name):
                self.llm.outcomes = outcomes
                resume_id = self.upload().json()["id"]
                body = self.get(resume_id).json()
                self.assertEqual(("failed", error_code), (body["status"], body["error_code"]))
                self.assertIsNone(body["parsed_data"])

    def test_llm_not_configured_fails_as_unavailable(self) -> None:
        app.dependency_overrides[deps.get_llm_client] = lambda: None

        resume_id = self.upload().json()["id"]

        self.assertEqual("llm_unavailable", self.get(resume_id).json()["error_code"])

    def test_retry_failed_resume(self) -> None:
        self.llm.outcomes = [LLMUnavailableError("timeout"), extraction()]
        resume_id = self.upload().json()["id"]

        response = self.client.post(f"/resumes/{resume_id}/retry", headers=self.headers)

        self.assertEqual(202, response.status_code)
        body = self.get(resume_id).json()
        self.assertEqual(("parsed", None), (body["status"], body["error_code"]))

    def test_retry_only_from_failed(self) -> None:
        resume_id = self.upload().json()["id"]

        response = self.client.post(f"/resumes/{resume_id}/retry", headers=self.headers)

        self.assertEqual(409, response.status_code)

    def test_lost_job_shows_as_failed(self) -> None:
        resume_id = self.upload().json()["id"]
        self.set_resume(
            resume_id, status="parsing", updated_at=datetime.now(UTC) - timedelta(minutes=11)
        )

        body = self.get(resume_id).json()

        self.assertEqual(("failed", "internal"), (body["status"], body["error_code"]))

    def test_other_users_resume_is_not_found(self) -> None:
        resume_id = self.upload().json()["id"]
        other = self.sign_up(uuid.uuid4(), "eve@example.com")

        for method, path in (
            ("get", f"/resumes/{resume_id}"),
            ("post", f"/resumes/{resume_id}/retry"),
            ("post", f"/resumes/{resume_id}/confirm"),
        ):
            with self.subTest(path):
                response = self.client.request(method, path, json={}, headers=other)
                self.assertEqual(404, response.status_code)

    def test_storage_failures(self) -> None:
        self.storage.fail = True
        self.assertEqual(503, self.upload().status_code)

        del app.dependency_overrides[deps.get_storage]
        settings = Settings(_env_file=None, database_url="postgresql+psycopg://x:y@localhost/z")
        with mock.patch.object(deps, "get_settings", return_value=settings):
            self.assertEqual(503, self.upload().status_code)

    # --- confirm -------------------------------------------------------------------------------

    def confirmed_body(self) -> dict:
        body = extraction().model_dump()
        body["skills"].append({"name": "python", "category": "language"})  # duplicate, other case
        body["projects"] = [{"name": "CareerGPS", "description": None, "url": None, "technologies": ["Next.js"]}]
        return body

    def test_confirm_writes_structured_tables(self) -> None:
        resume_id = self.upload().json()["id"]

        response = self.client.post(
            f"/resumes/{resume_id}/confirm", json=self.confirmed_body(), headers=self.headers
        )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("confirmed", response.json()["status"])
        with TestingSession() as db:
            self.assertEqual(1, len(db.scalars(select(Education)).all()))
            experience = db.scalars(select(Experience)).one()
            self.assertEqual("Built a FastAPI service\nCut test runtime by 40 percent", experience.description)
            self.assertEqual(["Python", "FastAPI"], [s.name for s in db.scalars(select(Skill)).all()])
            self.assertEqual(["Next.js"], db.scalars(select(Project)).one().technologies)
            profile = db.get(Profile, self.user_id)
            self.assertEqual("(608) 555-0100", profile.phone)
            self.assertEqual(["https://github.com/ada"], profile.links)
            self.assertIsNotNone(profile.onboarding_completed_at)

    def test_confirm_only_when_parsed(self) -> None:
        self.llm.outcomes = [LLMUnavailableError("timeout")]
        resume_id = self.upload().json()["id"]

        response = self.client.post(
            f"/resumes/{resume_id}/confirm", json=self.confirmed_body(), headers=self.headers
        )

        self.assertEqual(409, response.status_code)

    def test_confirm_validates_user_edits(self) -> None:
        resume_id = self.upload().json()["id"]
        cases = {
            "bad date": ("education", 0, "start_date", "Fall 2023"),
            "blank school": ("education", 0, "school", "  "),
            "unknown skill category": ("skills", 0, "category", "soft"),
        }
        for name, (section, index, field, value) in cases.items():
            with self.subTest(name):
                body = self.confirmed_body()
                body[section][index][field] = value
                response = self.client.post(
                    f"/resumes/{resume_id}/confirm", json=body, headers=self.headers
                )
                self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
