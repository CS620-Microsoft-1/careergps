import io
import os
import sys
import tempfile
import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import pymupdf
from docx import Document
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_resume_pipeline, get_token_verifier
from app.core.security import AuthenticatedUser, SupabaseTokenVerifier
from app.main import app
from app.services.foundry_agent import (
    ClassificationValidationError,
    FoundryAgentError,
    parse_json_response,
    validate_classification,
)
from app.services.resume_extraction import detect_file_type, extract_resume
from app.services.resume_pipeline import ResumePipeline
from tests.support import SUPABASE_URL, FakeJwks, new_signing_key


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def make_docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def classification_fixture() -> dict:
    return {
        "personal_information": {
            "name": "Ada Lovelace",
            "emails": ["ada@example.test", "ada@university.example"],
            "phones": [],
            "location": None,
            "linkedin": None,
            "github": None,
            "website": None,
        },
        "research_interests": [],
        "education": [],
        "work_experience": [],
        "research_experience": [],
        "projects": [],
        "technical_skills": ["Python"],
        "languages": [],
        "publications": [],
        "awards_honors": [],
        "certifications": [],
        "leadership_activities": [],
        "other": [],
    }


class ExtractionTests(unittest.TestCase):
    def test_detects_real_file_content_instead_of_filename(self) -> None:
        self.assertEqual(".pdf", detect_file_type(make_pdf("Ada Lovelace")))
        self.assertEqual(".docx", detect_file_type(make_docx("Grace Hopper")))
        with self.assertRaises(ValueError):
            detect_file_type(b"not a resume")

    def test_extracts_pdf_and_docx_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "resume.pdf"
            pdf_path.write_bytes(
                make_pdf("Ada Lovelace software engineer with Python and analytical experience")
            )
            docx_path = Path(directory) / "resume.docx"
            docx_path.write_bytes(make_docx("Grace Hopper computer scientist"))

            pdf = extract_resume(pdf_path, ".pdf")
            docx = extract_resume(docx_path, ".docx")

        self.assertIn("Ada Lovelace", pdf["text"])
        self.assertEqual("PyMuPDF", pdf["parser"])
        self.assertIn("Grace Hopper", docx["text"])
        self.assertEqual("python-docx", docx["parser"])


class ClassificationTests(unittest.TestCase):
    def test_parses_fenced_json_and_validates_fixed_schema(self) -> None:
        import json

        payload = parse_json_response(f"```json\n{json.dumps(classification_fixture())}\n```")
        result = validate_classification(payload)
        self.assertEqual("Ada Lovelace", result["personal_information"]["name"])
        self.assertEqual(["Python"], result["technical_skills"])

    def test_normalizes_legacy_contacts_and_explicit_date_range(self) -> None:
        payload = deepcopy(classification_fixture())
        personal = payload["personal_information"]
        personal.pop("emails")
        personal.pop("phones")
        personal["email"] = "ada@example.test"
        personal["phone"] = "+1 555 010 1000"
        personal["other_contacts"] = ["ada@university.example", "+1 555 010 2000"]
        payload["work_experience"] = [
            {
                "company": "Analytical Engines",
                "title": "Research Intern",
                "start_date": "May 11 - Jul 23, 2026",
                "end_date": None,
                "location": "London",
                "content": [],
            }
        ]
        payload["education"] = [
            {
                "institution": "Example University",
                "degree": "Bachelor of Science in Computer Science",
                "field_of_study": None,
                "start_date": None,
                "end_date": "Expected May 2027",
                "gpa": None,
                "content": [
                    "Minors/Certificates: Technical Communication",
                    "Relevant Coursework: Algorithms",
                ],
            }
        ]
        payload["awards_honors"] = [
            {
                "name": "Analytical Engine Prize",
                "issuer": None,
                "date": None,
                "content": "Awarded for original research.",
            }
        ]

        result = validate_classification(payload)

        self.assertEqual(
            ["ada@example.test", "ada@university.example"],
            result["personal_information"]["emails"],
        )
        self.assertEqual(
            ["(555) 010-1000", "(555) 010-2000"],
            result["personal_information"]["phones"],
        )
        self.assertEqual("2026-05", result["work_experience"][0]["start_date"])
        self.assertEqual("2026-07", result["work_experience"][0]["end_date"])
        self.assertEqual("Computer Science", result["education"][0]["major"])
        self.assertEqual("Bachelor of Science", result["education"][0]["degree"])
        self.assertEqual("2027-05", result["education"][0]["end_date"])
        self.assertEqual(
            ["Relevant Coursework: Algorithms"],
            result["education"][0]["content"],
        )
        self.assertEqual("Technical Communication", result["certifications"][0]["name"])
        self.assertEqual(
            ["Awarded for original research."],
            result["awards_honors"][0]["content"],
        )

    def test_rejects_unknown_categories(self) -> None:
        with self.assertRaises(ClassificationValidationError):
            validate_classification({"Invented Category": []})


class FakeAgent:
    agent_name = "test-agent"

    def classify(self, extracted_resume_text: str) -> dict:
        return classification_fixture()


def make_blank_pdf() -> bytes:
    document = pymupdf.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    return data


class PipelineStepTests(unittest.TestCase):
    def analyze(self, data: bytes) -> list[tuple]:
        steps: list[tuple] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume.pdf"
            path.write_bytes(data)
            ResumePipeline(FakeAgent()).analyze(
                path, ".pdf", "resume.pdf", on_step=lambda *step: steps.append(step)
            )
        return steps

    def test_reports_steps_in_order_without_ocr_for_a_text_pdf(self) -> None:
        steps = self.analyze(
            make_pdf("Ada Lovelace software engineer with Python and analytical experience")
        )

        self.assertEqual(
            [("extract", "started"), ("extract", "done"), ("classify", "started"), ("classify", "done")],
            [step[:2] for step in steps],
        )
        self.assertEqual("PyMuPDF", steps[1][2]["parser"])
        self.assertEqual([], steps[1][2]["ocr_pages"])
        self.assertTrue(steps[3][2]["validated"])

    def test_reports_ocr_steps_for_an_image_only_page(self) -> None:
        def fake_ocrmypdf(command: list[str], **kwargs) -> CompletedProcess:
            # Stand in for OCRmyPDF: write a PDF that now has a text layer.
            Path(command[-1]).write_bytes(make_pdf("Ada Lovelace scanned résumé with Python experience"))
            return CompletedProcess(command, 0)

        with mock.patch("app.services.resume_extraction.subprocess.run", side_effect=fake_ocrmypdf):
            steps = self.analyze(make_blank_pdf())

        self.assertEqual(
            [
                ("extract", "started"),
                ("ocr", "started"),
                ("ocr", "done"),
                ("extract", "done"),
                ("classify", "started"),
                ("classify", "done"),
            ],
            [step[:2] for step in steps],
        )
        self.assertEqual({"pages": [1]}, steps[1][2])
        self.assertEqual([1], steps[3][2]["ocr_pages"])


class FakePipeline:
    def __init__(self, error: Exception | None = None) -> None:
        self.temporary_path: Path | None = None
        self.error = error

    def analyze(self, path: Path, suffix: str, filename: str, on_step=None) -> dict:
        self.temporary_path = path
        self.assertions(path, suffix)
        report = on_step or (lambda *step: None)
        report("extract", "started", None)
        report("extract", "done", {"parser": "PyMuPDF", "characters": 12, "ocr_pages": []})
        report("classify", "started", None)
        if self.error:
            raise self.error
        report("classify", "done", {"seconds": 0.01, "validated": True})
        return {
            "filename": filename,
            "extraction": {
                "parser": "PyMuPDF",
                "ocr_pages": [],
                "characters": 12,
                "seconds": 0.001,
                "text": "Ada Lovelace",
            },
            "agent": {"name": "test-agent", "seconds": 0.01, "validated": True},
            "classification": classification_fixture(),
        }

    @staticmethod
    def assertions(path: Path, suffix: str) -> None:
        if not path.exists() or suffix != ".pdf":
            raise AssertionError("The route did not create the expected temporary PDF")


class ResumeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = FakePipeline()
        app.dependency_overrides[get_resume_pipeline] = lambda: self.pipeline
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=uuid.uuid4(), email="ada@example.com")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_analyze_returns_result_and_deletes_temporary_file(self) -> None:
        response = self.client.post(
            "/resumes/analyze",
            files={"file": ("resume.pdf", make_pdf("Ada Lovelace"), "application/pdf")},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("Ada Lovelace", response.json()["classification"]["personal_information"]["name"])
        self.assertIsNotNone(self.pipeline.temporary_path)
        self.assertFalse(self.pipeline.temporary_path.exists())

    def test_rejects_non_resume_content(self) -> None:
        response = self.client.post(
            "/resumes/analyze",
            files={"file": ("resume.pdf", b"not really a pdf", "application/pdf")},
        )
        self.assertEqual(415, response.status_code)

    def test_requires_login(self) -> None:
        del app.dependency_overrides[get_current_user]
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(new_signing_key()))
        app.dependency_overrides[get_token_verifier] = lambda: verifier

        response = self.client.post(
            "/resumes/analyze",
            files={"file": ("resume.pdf", make_pdf("Ada Lovelace"), "application/pdf")},
        )

        self.assertEqual(401, response.status_code)
        self.assertIsNone(self.pipeline.temporary_path)

    def stream(self, data: bytes) -> tuple[int, list[dict]]:
        import json

        response = self.client.post(
            "/resumes/analyze/stream",
            files={"file": ("resume.pdf", data, "application/pdf")},
        )
        if response.status_code != 200:
            return response.status_code, []
        self.assertTrue(response.headers["content-type"].startswith("application/x-ndjson"))
        return 200, [json.loads(line) for line in response.text.splitlines()]

    def test_stream_sends_each_step_then_the_result(self) -> None:
        status_code, events = self.stream(make_pdf("Ada Lovelace"))

        self.assertEqual(200, status_code)
        self.assertEqual(
            [
                ("step", "upload", "done"),
                ("step", "extract", "started"),
                ("step", "extract", "done"),
                ("step", "classify", "started"),
                ("step", "classify", "done"),
                ("result", None, None),
            ],
            [(event["type"], event.get("step"), event.get("status")) for event in events],
        )
        self.assertEqual("pdf", events[0]["detail"]["file_type"])
        self.assertEqual({}, events[1]["detail"])
        self.assertEqual(
            "Ada Lovelace", events[-1]["data"]["classification"]["personal_information"]["name"]
        )
        self.assertFalse(self.pipeline.temporary_path.exists())

    def test_stream_rejects_non_resume_content_before_streaming(self) -> None:
        status_code, events = self.stream(b"not really a pdf")

        self.assertEqual(415, status_code)
        self.assertIsNone(self.pipeline.temporary_path)

    def test_stream_reports_agent_failure_as_an_error_event(self) -> None:
        self.pipeline.error = FoundryAgentError("The Foundry Agent is not configured on the backend.")

        status_code, events = self.stream(make_pdf("Ada Lovelace"))

        self.assertEqual(200, status_code)
        self.assertEqual(("step", "classify", "started"), (events[-2]["type"], events[-2]["step"], events[-2]["status"]))
        self.assertEqual(
            {"type": "error", "status": 503, "detail": "The Foundry Agent is not configured on the backend."},
            events[-1],
        )
        self.assertFalse(self.pipeline.temporary_path.exists())

    def test_stream_reports_unexpected_failure_without_internal_details(self) -> None:
        self.pipeline.error = RuntimeError("secret internal detail")

        with self.assertLogs("app.api.routes.resumes", level="ERROR"):
            status_code, events = self.stream(make_pdf("Ada Lovelace"))

        self.assertEqual(200, status_code)
        self.assertEqual(500, events[-1]["status"])
        self.assertNotIn("secret", events[-1]["detail"])

    def test_stream_requires_login(self) -> None:
        del app.dependency_overrides[get_current_user]
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(new_signing_key()))
        app.dependency_overrides[get_token_verifier] = lambda: verifier

        status_code, _ = self.stream(make_pdf("Ada Lovelace"))

        self.assertEqual(401, status_code)
        self.assertIsNone(self.pipeline.temporary_path)


if __name__ == "__main__":
    unittest.main()
