"""One analysis HTTP entry point with fake Agent and local-only result storage."""

import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.deps import get_job_analysis_pipeline
from app.api.routes.job_postings import router
from app.core.config import get_settings
from app.models.job_posting import JobPosting
from app.services.job_posting_analysis_pipeline import (
    JobPostingAnalysisPipeline, ReadOnlyJobPostingSource,
)
from app.services.local_job_analysis_store import LocalAnalysisStateError, LocalJobAnalysisStore
from tests.test_job_posting_analysis_pipeline import DESCRIPTION, FakeAgent, analysis_fixture

ADMIN_HEADERS = {"X-Job-Analysis-Token": "test-local-admin"}


class JobPostingsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        # A remote analysis table is intentionally absent in this test database.
        JobPosting.__table__.create(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self.agent = FakeAgent()
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "job_analyses"
        self.store = LocalJobAnalysisStore(self.directory)
        self.source = ReadOnlyJobPostingSource(self.session_factory)
        self.pipeline = JobPostingAnalysisPipeline(self.source, self.store, self.agent)
        self.job_id = uuid.uuid4()
        now = datetime(2026, 10, 20, 10, 15, 30, 123456, tzinfo=UTC)
        with self.session_factory() as session, session.begin():
            session.add(JobPosting(
                id=self.job_id, source="greenhouse", external_id="http-example-1",
                company_slug="example", company_name="Example", company_tier="other",
                title="Software Engineer", location="Example City", country=None,
                workplace_type=None, department="Engineering", employment_type=None,
                description_text=DESCRIPTION, salary_min=None, salary_max=None,
                salary_currency=None, salary_interval=None,
                url="https://example.test/jobs/1?source=http&lang=en",
                published_at=now, first_seen_at=now, last_seen_at=now, closed_at=None,
                content_hash="0" * 64, created_at=now, updated_at=now,
            ))
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_job_analysis_pipeline] = lambda: self.pipeline
        self.set_admin_token("test-local-admin")
        self.client = TestClient(self.app)
        self.path = f"/job-postings/{self.job_id}/analyze"

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        self.temporary.cleanup()

    def set_admin_token(self, value: str | None) -> None:
        settings = SimpleNamespace(
            job_analysis_admin_token=SecretStr(value) if value is not None else None,
        )
        self.app.dependency_overrides[get_settings] = lambda: settings

    def exported(self) -> Path:
        return self.directory / "results" / f"{self.job_id}.json"

    def test_single_post_analyzes_and_returns_original_28_fields(self) -> None:
        source_before = self.source.get_posting(self.job_id)
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda _c, _cu, sql, _p, _ctx, _many: statements.append(sql))
        response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(200, response.status_code)
        result = response.json()
        self.assertEqual({"job_posting_id", "status", "structured_data", "error_message"}, set(result))
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(str(self.job_id), result["job_posting_id"])
        self.assertEqual(28, len(result["structured_data"]))
        self.assertEqual(analysis_fixture(self.job_id, posting=source_before), result["structured_data"])
        self.assertEqual(result["structured_data"], json.loads(self.exported().read_text()))
        self.assertEqual(result, self.store.get(str(self.job_id)))
        self.assertEqual([source_before], self.agent.calls)
        self.assertEqual(source_before, self.source.get_posting(self.job_id))
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in statements))
        self.assertTrue(all("job_postings_analyses" not in sql for sql in statements))

    def test_router_exposes_only_one_post_and_no_previous_get_endpoints(self) -> None:
        routes = [route for route in router.routes if getattr(route, "path", "").startswith("/job-postings/")]
        self.assertEqual(1, len(routes))
        self.assertEqual({"POST"}, routes[0].methods)
        self.assertEqual("/job-postings/{job_posting_id}/analyze", routes[0].path)
        for path in (f"/job-postings/{self.job_id}", f"/job-postings/{self.job_id}/analysis"):
            with self.subTest(path=path):
                self.assertEqual(404, self.client.get(path).status_code)
        self.assertEqual([], self.agent.calls)

    def test_successful_result_is_cached_without_repeat_agent_call(self) -> None:
        first = self.client.post(self.path, headers=ADMIN_HEADERS)
        original_file = self.exported().read_bytes()
        second = self.client.post(self.path, headers=ADMIN_HEADERS, json={})
        self.assertEqual(200, second.status_code)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(1, len(self.agent.calls))
        self.assertEqual(original_file, self.exported().read_bytes())

    def test_explicit_force_refresh_replaces_only_local_result(self) -> None:
        self.client.post(self.path, headers=ADMIN_HEADERS)
        updated = analysis_fixture(self.job_id, posting=self.source.get_posting(self.job_id), include_overview=True)
        self.agent.behavior = lambda _posting: updated
        response = self.client.post(self.path, headers=ADMIN_HEADERS, json={"force": True})
        self.assertEqual(200, response.status_code)
        self.assertEqual(updated, response.json()["structured_data"])
        self.assertEqual(updated, json.loads(self.exported().read_text()))
        self.assertEqual(2, len(self.agent.calls))
        self.assertEqual(["job_postings"], inspect(self.engine).get_table_names())

    def test_force_does_not_take_over_running_local_work(self) -> None:
        self.pipeline.enqueue(self.job_id)
        self.assertIsNotNone(self.store.claim(str(self.job_id), force=False))
        response = self.client.post(self.path, headers=ADMIN_HEADERS, json={"force": True})
        self.assertEqual(202, response.status_code)
        self.assertEqual("running", response.json()["status"])
        self.assertEqual([], self.agent.calls)
        self.assertFalse(self.exported().exists())

    def test_invalid_agent_result_is_reported_as_local_failure(self) -> None:
        self.agent.behavior = lambda _posting: {"not": "the 28-field schema"}
        response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(200, response.status_code)
        self.assertEqual("failed", response.json()["status"])
        self.assertIsNone(response.json()["structured_data"])
        self.assertIsNotNone(response.json()["error_message"])
        self.assertFalse(self.exported().exists())
        self.assertEqual(response.json(), self.store.get(str(self.job_id)))

    def test_invalid_evidence_returns_safe_local_failure_without_export(self) -> None:
        def invalid(posting):
            data = analysis_fixture(posting["id"], posting=posting)
            data["qualifications"][0]["evidence"][0]["quote"] = "private invented evidence"
            return data

        self.agent.behavior = invalid
        response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(200, response.status_code)
        result = response.json()
        self.assertEqual("failed", result["status"])
        self.assertIsNone(result["structured_data"])
        self.assertIn("evidence_quote_not_in_source", result["error_message"])
        self.assertNotIn("private", response.text)
        self.assertFalse(self.exported().exists())
        self.assertEqual(result, self.store.get(str(self.job_id)))

    def test_failed_force_preserves_old_result_and_does_not_expose_sdk_error(self) -> None:
        first = self.client.post(self.path, headers=ADMIN_HEADERS).json()
        previous_file = self.exported().read_bytes()
        self.agent.behavior = lambda _posting: (_ for _ in ()).throw(RuntimeError("private SDK error"))
        response = self.client.post(self.path, headers=ADMIN_HEADERS, json={"force": True})
        self.assertEqual(200, response.status_code)
        self.assertEqual("failed", response.json()["status"])
        self.assertEqual(first["structured_data"], response.json()["structured_data"])
        self.assertNotIn("private", response.text)
        self.assertEqual(previous_file, self.exported().read_bytes())

    def test_unknown_source_is_404_without_creating_local_queue_work(self) -> None:
        missing = str(uuid.uuid4())
        response = self.client.post(f"/job-postings/{missing}/analyze", headers=ADMIN_HEADERS)
        self.assertEqual(404, response.status_code)
        self.assertEqual({"detail": "The source job posting was not found."}, response.json())
        self.assertIsNone(self.store.get(missing))
        self.assertEqual([], self.agent.calls)

    def test_invalid_uuid_and_request_body_are_rejected(self) -> None:
        cases = (
            ("/job-postings/not-a-uuid/analyze", {}),
            (self.path, {"force": "true"}),
            (self.path, {"force": 1}),
            (self.path, {"unexpected": True}),
        )
        for path, body in cases:
            with self.subTest(path=path, body=body):
                response = self.client.post(path, headers=ADMIN_HEADERS, json=body)
                self.assertEqual(422, response.status_code)
        self.assertEqual([], self.agent.calls)
        self.assertIsNone(self.store.next_queued_id())

    def test_missing_or_invalid_management_token_prevents_analysis(self) -> None:
        for headers in ({}, {"X-Job-Analysis-Token": "wrong"}):
            with self.subTest(headers=headers):
                response = self.client.post(self.path, headers=headers)
                self.assertEqual(401, response.status_code)
        self.assertEqual([], self.agent.calls)
        self.assertIsNone(self.store.next_queued_id())

    def test_unconfigured_management_token_disables_endpoint(self) -> None:
        self.set_admin_token(None)
        response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(503, response.status_code)
        self.assertEqual([], self.agent.calls)
        self.assertIsNone(self.store.next_queued_id())

    def test_source_failure_is_sanitized_503(self) -> None:
        error = OperationalError("secret SQL", {}, RuntimeError("secret credentials"))
        with patch.object(self.pipeline, "analyze", side_effect=error):
            response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(503, response.status_code)
        self.assertEqual({"detail": "The job posting database is unavailable."}, response.json())
        self.assertNotIn("secret", response.text)

    def test_local_storage_failures_are_sanitized_503(self) -> None:
        for error in (sqlite3.OperationalError("secret local path"), OSError("secret local path")):
            with self.subTest(error=type(error).__name__), patch.object(self.pipeline, "analyze", side_effect=error):
                response = self.client.post(self.path, headers=ADMIN_HEADERS)
                self.assertEqual(503, response.status_code)
                self.assertEqual({"detail": "The local job analysis storage is unavailable."}, response.json())
                self.assertNotIn("secret", response.text)

    def test_local_storage_initialization_failure_is_sanitized_503(self) -> None:
        del self.app.dependency_overrides[get_job_analysis_pipeline]
        settings = SimpleNamespace(
            job_analysis_project_endpoint="https://example.test/project",
            job_analysis_timeout_seconds=600,
            job_analysis_local_dir=self.directory,
        )
        for error in (sqlite3.OperationalError("secret path"), OSError("secret path")):
            with (
                self.subTest(error=type(error).__name__),
                patch("app.api.deps.get_settings", return_value=settings),
                patch("app.api.deps.FoundryJobPostingAnalysisService") as agent,
                patch("app.api.deps.LocalJobAnalysisStore", side_effect=error),
            ):
                response = self.client.post(self.path, headers=ADMIN_HEADERS)
                self.assertEqual(503, response.status_code)
                self.assertEqual(
                    {"detail": "The local job analysis storage is unavailable."}, response.json()
                )
                self.assertNotIn("secret", response.text)
                agent.return_value.analyze.assert_not_called()

    def test_post_recovers_expired_local_attempt_before_analyzing(self) -> None:
        clock = [1000.0]
        self.store.clock = lambda: clock[0]
        self.pipeline.enqueue(self.job_id)
        old_attempt = self.store.claim(str(self.job_id))
        clock[0] += 121
        response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(200, response.status_code)
        self.assertEqual("succeeded", response.json()["status"])
        self.assertEqual(28, len(response.json()["structured_data"]))
        self.assertEqual(1, len(self.agent.calls))
        with self.assertRaises(LocalAnalysisStateError):
            self.store.finish(str(self.job_id), old_attempt, data=analysis_fixture(self.job_id))

    def test_failed_agent_result_is_not_automatically_retried(self) -> None:
        self.agent.behavior = lambda _posting: {"bad": "format"}
        first = self.client.post(self.path, headers=ADMIN_HEADERS)
        second = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual("failed", first.json()["status"])
        self.assertEqual(first.json(), second.json())
        self.assertEqual(1, len(self.agent.calls))

    def test_lost_lease_returns_safe_conflict_instead_of_stale_result(self) -> None:
        with patch.object(self.pipeline, "analyze", side_effect=LocalAnalysisStateError("private path")):
            response = self.client.post(self.path, headers=ADMIN_HEADERS)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("private", response.text)
        self.assertEqual([], self.agent.calls)

    def test_real_main_registers_the_route_with_fake_dependencies(self) -> None:
        # Importing the app constructs no source connection and calls no Agent.
        from app.main import app as main_app

        original_overrides = main_app.dependency_overrides.copy()
        main_app.dependency_overrides[get_job_analysis_pipeline] = lambda: self.pipeline
        main_app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            job_analysis_admin_token=SecretStr("test-local-admin"),
        )
        try:
            with TestClient(main_app) as client:
                response = client.post(self.path, headers=ADMIN_HEADERS)
            self.assertEqual(200, response.status_code)
            self.assertEqual("succeeded", response.json()["status"])
            self.assertEqual(1, len(self.agent.calls))
            self.assertTrue(self.exported().exists())
        finally:
            main_app.dependency_overrides.clear()
            main_app.dependency_overrides.update(original_overrides)


if __name__ == "__main__":
    unittest.main()
