"""Offline JD tests: read source rows, keep every analysis write in a local store."""

import json
import subprocess
import threading
import sys
import tempfile
import unittest
import uuid
from copy import deepcopy
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.job_posting import JobPosting
from app.services.job_posting_analysis_agent import (
    JobPostingAnalysisAgentError,
    JobPostingAnalysisInputError,
)
from app.services.local_job_analysis_store import LocalAnalysisStateError, LocalJobAnalysisStore
from app.services.job_posting_analysis_pipeline import (
    JobPostingAnalysisPipeline,
    JobPostingNotFoundError,
    JobPostingSourceReadOnlyError,
    ReadOnlyJobPostingSource,
    SupabaseAnalysisPersistenceNotEnabled,
    save_analysis_to_supabase,
    is_focus_job_title,
)

from tests.test_job_posting_analysis_agent import (
    analysis_fixture as agent_analysis_fixture,
    posting_fixture as agent_posting_fixture,
)

ROLE_PURPOSE = "Build reliable services."
DESCRIPTION = f"Must have Python or Go. {ROLE_PURPOSE} Base salary: $100,000–$120,000 per year."


def analysis_fixture(
    job_id: uuid.UUID | str, *, label: str = "Python or Go",
    posting: dict | None = None, include_overview: bool = False,
) -> dict:
    """Build a schema fixture; supplied source data makes metadata content-valid."""
    result = agent_analysis_fixture()
    result["id"] = str(job_id)
    if posting is not None:
        copied_fields = (
            "source", "external_id", "company_slug", "company_tier", "url",
            "published_at", "first_seen_at", "last_seen_at", "closed_at",
            "content_hash", "created_at", "updated_at",
        )
        for field in copied_fields:
            original = posting.get(field)
            result[field] = original if original not in (None, "") else None
    result["company_name"] = posting.get("company_name") if posting else None
    result["job_title"] = posting.get("title") if posting else None
    if include_overview:
        result["role_overview"] = {
            "value": ROLE_PURPOSE,
            "evidence": [{"source_field": "description_text", "quote": ROLE_PURPOSE}],
        }
    result["qualifications"] = [{
        "value": f"Must have {label}.",
        "level": "required",
        "categories": ["skill"],
        "evidence": [{"source_field": "description_text", "quote": f"Must have {label}."}],
    }]
    result["compensation"] = [{
        "type": "base_salary",
        "value": "Base salary: $100,000–$120,000 per year.",
        "minimum": 100000,
        "maximum": 120000,
        "currency": None,
        "interval": "year",
        "applies_to": None,
        "evidence": [{
            "source_field": "description_text",
            "quote": "Base salary: $100,000–$120,000 per year.",
        }],
    }]
    return result


class FakeAgent:
    def __init__(self) -> None:
        self.calls = []
        self.behavior = None

    def analyze(self, posting: dict) -> dict:
        self.calls.append(deepcopy(posting))
        if self.behavior is not None:
            return self.behavior(posting)
        return analysis_fixture(posting["id"], posting=posting)


class JobPostingAnalysisPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        # Intentionally do not create job_postings_analyses: nothing may write it.
        JobPosting.__table__.create(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "job_analyses"
        self.store = LocalJobAnalysisStore(self.directory)
        self.agent = FakeAgent()
        self.source = ReadOnlyJobPostingSource(self.session_factory)
        self.pipeline = JobPostingAnalysisPipeline(self.source, self.store, self.agent)
        self.job_id = self.add_posting("example-1")
        self.source_sql = []
        self.record_sql = False

        @event.listens_for(self.engine, "before_cursor_execute")
        def record_statement(_connection, _cursor, statement, _params, _context, _many):
            if self.record_sql:
                self.source_sql.append(statement)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temporary.cleanup()

    def add_posting(self, external_id: str, *, title: str = "Software Engineer") -> uuid.UUID:
        now = datetime(2026, 10, 20, 10, 15, 30, 123456, tzinfo=UTC)
        with self.session_factory() as session, session.begin():
            posting = JobPosting(
                id=uuid.uuid4(), source="greenhouse", external_id=external_id,
                company_slug="example", company_name="Example", company_tier="other",
                title=title, location="Example City", country=None,
                workplace_type=None, department="Engineering", employment_type=None,
                description_text=DESCRIPTION, salary_min=None, salary_max=None,
                salary_currency=None, salary_interval=None,
                url=f"https://example.test/jobs/{external_id}?source=test&lang=en",
                published_at=now, first_seen_at=now, last_seen_at=now, closed_at=None,
                content_hash="0" * 64, created_at=now, updated_at=now,
            )
            session.add(posting)
            session.flush()
            return posting.id

    def exported(self, job_id=None) -> Path:
        return self.directory / "results" / f"{job_id or self.job_id}.json"

    def test_focus_title_match_is_conservative_and_case_insensitive(self) -> None:
        for title in ("Software Engineer", "Senior Software Engineer, Backend", "DATA ANALYST Intern",
                      "AI-Engineer", "Software  Engineer II", "AI–Engineer (New Grad)"):
            with self.subTest(title=title):
                self.assertTrue(is_focus_job_title(title))
        for title in (None, "", 42, "Retail Engineer", "Software Engineering Manager",
                      "Metadata Analyst", "Sustaining AI Engineering", "Artificial Intelligence Engineer"):
            with self.subTest(title=title):
                self.assertFalse(is_focus_job_title(title))

    def test_focused_discovery_filters_before_enqueuing_and_preserves_states(self) -> None:
        selected = [self.job_id, self.add_posting("data", title="Data Analyst"),
                    self.add_posting("ai", title="AI Engineer Intern")]
        excluded = [self.add_posting("retail", title="Retail Engineer"),
                    self.add_posting("engineering", title="Software Engineering Manager")]
        self.record_sql = True
        self.assertEqual(self.pipeline.enqueue_missing(batch_size=1, focused_only=True, limit=3), 3)
        self.assertEqual(self.pipeline.enqueue_missing(batch_size=1, focused_only=True, limit=3), 0)
        for job_id in selected:
            self.assertEqual(self.store.get(str(job_id))["status"], "queued")
        for job_id in excluded:
            self.assertIsNone(self.store.get(str(job_id)))
        self.assertEqual(self.agent.calls, [])
        self.assertTrue(all("description_text" not in sql for sql in self.source_sql))
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in self.source_sql))

    def test_worker_budget_limits_real_queue_and_skips_preexisting_unrelated_job(self) -> None:
        from scripts.job_posting_analysis_worker import run_worker

        with self.session_factory() as session, session.begin():
            session.get(JobPosting, self.job_id).title = "Retail Engineer"
        ids = [self.add_posting(f"budget-{n}", title="Senior Software Engineer") for n in range(6)]
        self.store.enqueue_many([str(self.job_id), *(str(job_id) for job_id in ids)])
        self.assertEqual(run_worker(self.pipeline), 0)
        self.assertEqual(len(self.agent.calls), 3)
        self.assertTrue(all(is_focus_job_title(posting["title"]) for posting in self.agent.calls))
        self.assertEqual(self.store.get(str(self.job_id))["status"], "queued")
        self.assertEqual(sum(self.store.get(str(job_id))["status"] == "queued" for job_id in ids), 3)

    def test_worker_discovers_at_most_three_from_large_unqueued_source(self) -> None:
        from scripts.job_posting_analysis_worker import run_worker

        ids = [self.job_id, *(self.add_posting(f"discover-{n}") for n in range(8))]
        self.assertEqual(run_worker(self.pipeline), 0)
        self.assertEqual(len(self.agent.calls), 3)
        self.assertEqual(sum(self.store.get(str(job_id)) is not None for job_id in ids), 3)

    def test_unrelated_only_queue_is_idle_but_manual_single_id_can_analyze(self) -> None:
        with self.session_factory() as session, session.begin():
            session.get(JobPosting, self.job_id).title = "Retail Engineer"
        self.pipeline.enqueue(self.job_id)
        self.assertIsNone(self.pipeline.process_next(focused_only=True))
        self.assertEqual(self.agent.calls, [])
        self.assertEqual(self.store.get(str(self.job_id))["status"], "queued")
        self.assertEqual(self.pipeline.analyze(self.job_id)["status"], "succeeded")
        self.assertEqual(len(self.agent.calls), 1)

    def test_worker_rechecks_changed_title_after_claim_without_calling_agent(self) -> None:
        self.pipeline.enqueue(self.job_id)
        original = self.source.get_posting(self.job_id)
        changed = {**original, "title": "Retail Engineer"}
        with patch.object(self.source, "get_posting", return_value=changed):
            result = self.pipeline.process_next(focused_only=True)
        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.agent.calls, [])
        self.assertIsNone(self.store.get(str(self.job_id))["structured_data"])

    def test_idle_focus_skip_cache_refreshes_on_worker_scan(self) -> None:
        self.pipeline.enqueue(self.job_id)
        with self.session_factory() as session, session.begin():
            session.get(JobPosting, self.job_id).title = "Retail Engineer"
        self.source_sql.clear()
        self.record_sql = True
        self.assertIsNone(self.pipeline.process_next(focused_only=True))
        self.assertEqual(len(self.source_sql), 1)
        self.assertNotIn("description_text", self.source_sql[0])
        self.source_sql.clear()
        self.assertIsNone(self.pipeline.process_next(focused_only=True))
        self.assertEqual(self.source_sql, [])
        self.record_sql = False
        with self.session_factory() as session, session.begin():
            session.get(JobPosting, self.job_id).title = "AI Engineer"
        self.assertIsNone(self.pipeline.process_next(focused_only=True))
        self.assertEqual(self.agent.calls, [])
        self.pipeline.recover_interrupted()
        self.assertEqual(self.pipeline.process_next(focused_only=True)["status"], "succeeded")
        self.assertEqual(len(self.agent.calls), 1)

    def test_title_lookup_batches_large_legacy_queue(self) -> None:
        # Absent IDs need no full posting reads to discover their absence. The
        # same bounded lookup applies to hundreds of unrelated legacy entries.
        ids = [str(self.job_id), *(str(uuid.uuid4()) for _ in range(500))]
        self.source_sql.clear()
        self.record_sql = True
        self.assertEqual(self.source.get_titles(ids), {str(self.job_id): "Software Engineer"})
        self.assertEqual(len(self.source_sql), 2)
        self.assertTrue(all("description_text" not in sql for sql in self.source_sql))
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in self.source_sql))

    def test_focused_queue_records_deleted_source_without_calling_agent(self) -> None:
        self.pipeline.enqueue(self.job_id)
        with self.session_factory() as session, session.begin():
            session.delete(session.get(JobPosting, self.job_id))
        self.assertEqual(self.pipeline.process_next(focused_only=True)["status"], "failed")
        self.assertEqual(self.agent.calls, [])

    def test_get_posting_preserves_all_25_fields_and_nulls(self) -> None:
        with self.session_factory() as session:
            row = session.get(JobPosting, self.job_id)
            expected = {
                column.key: getattr(row, column.key)
                for column in inspect(JobPosting).columns
            }
        expected = {
            key: value.isoformat() if isinstance(value, datetime)
            else str(value) if isinstance(value, uuid.UUID) else value
            for key, value in expected.items()
        }
        actual = self.pipeline.get_posting(str(self.job_id))
        self.assertEqual(25, len(actual))
        self.assertEqual(expected, actual)
        self.assertIsNone(actual["salary_min"])
        self.assertIsNone(actual["closed_at"])
        self.assertEqual([], self.agent.calls)
        self.assertIsNone(self.store.get(str(self.job_id)))

    def test_local_get_analysis_needs_no_source_row_and_does_not_enqueue(self) -> None:
        missing_id = uuid.uuid4()
        self.assertIsNone(self.pipeline.get_analysis(missing_id))
        self.assertIsNone(self.pipeline.get_analysis(self.job_id))
        self.assertIsNone(self.store.next_queued_id())
        self.assertEqual([], self.agent.calls)

    def test_missing_source_cannot_be_newly_enqueued_or_analyzed(self) -> None:
        missing_id = uuid.uuid4()
        for operation in (self.pipeline.get_posting, self.pipeline.enqueue, self.pipeline.analyze):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(JobPostingNotFoundError):
                    operation(missing_id)
        self.assertIsNone(self.store.get(str(missing_id)))
        self.assertEqual([], self.agent.calls)

    def test_invalid_job_id_is_rejected(self) -> None:
        for operation in (self.pipeline.get_posting, self.pipeline.enqueue, self.pipeline.analyze):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(JobPostingAnalysisInputError):
                    operation("not-a-uuid")
        self.assertEqual([], self.agent.calls)

    def test_success_saves_exact_28_fields_and_evidence_to_local_json(self) -> None:
        source = self.pipeline.get_posting(self.job_id)
        expected = analysis_fixture(self.job_id, posting=source)
        result = self.pipeline.analyze(self.job_id)
        self.assertEqual({"job_posting_id", "status", "structured_data", "error_message"}, set(result))
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(expected, result["structured_data"])
        self.assertEqual(28, len(result["structured_data"]))
        self.assertIsNone(result["error_message"])
        self.assertEqual(expected, json.loads(self.exported().read_text(encoding="utf-8")))
        self.assertEqual(result, self.pipeline.get_analysis(self.job_id))
        self.assertEqual([source], self.agent.calls)
        self.assertEqual(source, self.pipeline.get_posting(self.job_id))
        self.assertEqual(["job_postings"], inspect(self.engine).get_table_names())

    def test_source_connections_close_before_agent_runs(self) -> None:
        checked_out = set()
        event.listen(self.engine, "checkout", lambda _dbapi, record, _proxy: checked_out.add(id(record)))
        event.listen(self.engine, "checkin", lambda _dbapi, record: checked_out.discard(id(record)))

        def check(posting):
            self.assertEqual(set(), checked_out)
            self.assertEqual("running", self.store.get(posting["id"])["status"])
            return analysis_fixture(posting["id"], posting=posting)

        self.agent.behavior = check
        self.assertEqual("succeeded", self.pipeline.analyze(self.job_id)["status"])

    def test_full_lifecycle_only_selects_from_source_database(self) -> None:
        self.record_sql = True
        self.pipeline.enqueue_missing(batch_size=1)
        result = self.pipeline.process_next()
        self.pipeline.get_posting(self.job_id)
        self.pipeline.get_analysis(self.job_id)
        self.assertEqual("succeeded", result["status"])
        self.assertTrue(self.source_sql)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in self.source_sql))
        self.assertTrue(all("job_postings_analyses" not in sql for sql in self.source_sql))

    def test_initial_backfill_processes_every_existing_posting_once(self) -> None:
        ids = {self.job_id, self.add_posting("example-2"), self.add_posting("example-3")}
        self.assertEqual(3, self.pipeline.enqueue_missing(batch_size=1))
        self.assertEqual([], self.agent.calls)
        results = []
        while (result := self.pipeline.process_next()) is not None:
            results.append(result)
        self.assertEqual({str(id) for id in ids}, {row["job_posting_id"] for row in results})
        self.assertTrue(all(row["status"] == "succeeded" for row in results))
        self.assertEqual(3, len(self.agent.calls))
        self.assertEqual(0, self.pipeline.enqueue_missing())
        self.assertIsNone(self.pipeline.process_next())

    def test_restart_reuses_local_state_and_finds_only_new_source_id(self) -> None:
        self.assertEqual(1, self.pipeline.enqueue_missing())
        self.pipeline.process_next()
        restarted = JobPostingAnalysisPipeline(
            ReadOnlyJobPostingSource(self.session_factory),
            LocalJobAnalysisStore(self.directory), self.agent,
        )
        self.assertEqual(0, restarted.enqueue_missing())
        new_id = self.add_posting("new-daily-2")
        self.assertEqual(1, restarted.enqueue_missing(batch_size=1))
        self.assertEqual(str(new_id), restarted.process_next()["job_posting_id"])
        self.assertEqual(2, len(self.agent.calls))
        self.assertIsNone(restarted.process_next())

    def test_same_id_content_updates_do_not_automatically_reanalyze(self) -> None:
        original = self.pipeline.analyze(self.job_id)
        with self.session_factory() as session, session.begin():
            row = session.get(JobPosting, self.job_id)
            row.description_text = "Must have a different skill."
            row.content_hash = "1" * 64
        self.assertEqual(0, self.pipeline.enqueue_missing())
        self.assertEqual(original, self.pipeline.get_analysis(self.job_id))
        self.assertIsNone(self.pipeline.process_next())
        self.assertEqual(1, len(self.agent.calls))

    def test_backfill_skips_every_existing_status_including_failed_and_running(self) -> None:
        succeeded = self.pipeline.analyze(self.job_id)
        failed_id = self.add_posting("failed")
        self.agent.behavior = lambda _posting: (_ for _ in ()).throw(JobPostingAnalysisAgentError("secret"))
        failed = self.pipeline.analyze(failed_id)
        running_id = self.add_posting("running")
        self.pipeline.enqueue(running_id)
        self.assertIsNotNone(self.store.claim(str(running_id), force=False))
        queued_id = self.add_posting("queued")
        queued = self.pipeline.enqueue(queued_id)
        before = {str(id): self.store.get(str(id)) for id in (self.job_id, failed_id, running_id, queued_id)}
        self.assertEqual(0, self.pipeline.enqueue_missing(batch_size=1))
        self.assertEqual(before, {id: self.store.get(id) for id in before})
        self.assertEqual("succeeded", succeeded["status"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual("queued", queued["status"])
        self.assertEqual(2, len(self.agent.calls))

    def test_backfill_limit_counts_only_newly_enqueued_rows(self) -> None:
        self.pipeline.enqueue(self.job_id)
        ids = {self.add_posting(f"limited-{index}") for index in range(3)}
        self.assertEqual(2, self.pipeline.enqueue_missing(batch_size=1, limit=2))
        self.assertEqual(2, sum(self.store.get(str(id)) is not None for id in ids))
        self.assertEqual(1, self.pipeline.enqueue_missing(limit=2))
        self.assertEqual(0, self.pipeline.enqueue_missing(limit=2))
        self.assertEqual([], self.agent.calls)

    def test_successful_result_is_cached_until_explicit_force(self) -> None:
        first = self.pipeline.analyze(self.job_id)
        self.assertEqual(first, self.pipeline.analyze(str(self.job_id)))
        self.assertEqual(1, len(self.agent.calls))
        new = analysis_fixture(self.job_id, posting=self.source.get_posting(self.job_id), include_overview=True)
        self.agent.behavior = lambda _posting: deepcopy(new)
        self.assertEqual(new, self.pipeline.analyze(self.job_id, force=True)["structured_data"])
        self.assertEqual(2, len(self.agent.calls))
        self.assertEqual(new, json.loads(self.exported().read_text(encoding="utf-8")))

    def test_failed_force_refresh_preserves_previous_successful_result_file(self) -> None:
        old = self.pipeline.analyze(self.job_id)["structured_data"]
        previous_file = self.exported().read_bytes()
        self.agent.behavior = lambda _posting: (_ for _ in ()).throw(RuntimeError("secret SDK failure"))
        failed = self.pipeline.analyze(self.job_id, force=True)
        self.assertEqual("failed", failed["status"])
        self.assertEqual(old, failed["structured_data"])
        self.assertNotIn("secret", failed["error_message"])
        self.assertEqual(previous_file, self.exported().read_bytes())
        self.assertEqual(0, self.pipeline.enqueue_missing())

    def test_force_never_takes_over_a_running_attempt(self) -> None:
        self.pipeline.enqueue(self.job_id)
        self.assertIsNotNone(self.store.claim(str(self.job_id), force=False))
        result = self.pipeline.analyze(self.job_id, force=True)
        self.assertEqual("running", result["status"])
        self.assertEqual([], self.agent.calls)
        self.assertFalse(self.exported().exists())

    def test_invalid_schema_result_is_failed_and_not_exported(self) -> None:
        self.agent.behavior = lambda _posting: {"id": str(self.job_id)}
        result = self.pipeline.analyze(self.job_id)
        self.assertEqual("failed", result["status"])
        self.assertIsNone(result["structured_data"])
        self.assertFalse(self.exported().exists())

    def test_cross_posting_id_result_is_failed_and_not_exported(self) -> None:
        self.agent.behavior = lambda _posting: analysis_fixture(uuid.uuid4())
        result = self.pipeline.analyze(self.job_id)
        self.assertEqual("failed", result["status"])
        self.assertIsNone(result["structured_data"])
        self.assertFalse(self.exported().exists())

    def test_content_failures_are_local_failed_records_without_result_exports(self) -> None:
        cases = (
            ("quote", "evidence_quote_not_in_source"),
            ("source", "unknown_evidence_source"),
            ("evidence", "missing_evidence"),
            ("metadata", "metadata_not_exact_copy"),
            ("salary", "monetary_bounds_reversed"),
        )
        for name, code in cases:
            with self.subTest(rule=name):
                job_id = self.add_posting(f"invalid-content-{name}")

                def invalid(posting, rule=name):
                    data = analysis_fixture(posting["id"], posting=posting)
                    requirement = data["qualifications"][0]
                    if rule == "quote":
                        requirement["evidence"][0]["quote"] = "private invented quote"
                    elif rule == "source":
                        requirement["evidence"][0]["source_field"] = "private missing field"
                    elif rule == "evidence":
                        requirement["evidence"] = []
                    elif rule == "metadata":
                        data["source"] = "private mutated source"
                    else:
                        data["compensation"][0]["minimum"] = 120001
                    return data

                self.agent.behavior = invalid
                result = self.pipeline.analyze(job_id)
                self.assertEqual("failed", result["status"])
                self.assertIsNone(result["structured_data"])
                self.assertIn(code, result["error_message"])
                self.assertNotIn("private", result["error_message"])
                self.assertNotIn(DESCRIPTION, result["error_message"])
                self.assertFalse(self.exported(job_id).exists())
                self.assertEqual(result, self.store.get(str(job_id)))

    def test_content_failure_on_force_preserves_previous_valid_result(self) -> None:
        previous = self.pipeline.analyze(self.job_id)["structured_data"]
        previous_file = self.exported().read_bytes()

        def invalid(posting):
            data = analysis_fixture(posting["id"], posting=posting)
            data["qualifications"][0]["evidence"][0]["quote"] = "private unsupported quote"
            return data

        self.agent.behavior = invalid
        result = self.pipeline.analyze(self.job_id, force=True)
        self.assertEqual("failed", result["status"])
        self.assertIn("evidence_quote_not_in_source", result["error_message"])
        self.assertEqual(previous, result["structured_data"])
        self.assertEqual(previous_file, self.exported().read_bytes())
        self.assertEqual(previous, json.loads(self.exported().read_text(encoding="utf-8")))

    def test_invalid_content_does_not_block_next_queued_job(self) -> None:
        next_id = self.add_posting("valid-after-content-failure")
        self.pipeline.enqueue(self.job_id)
        self.pipeline.enqueue(next_id)

        def first_invalid(posting):
            data = analysis_fixture(posting["id"], posting=posting)
            if posting["id"] == str(self.job_id):
                data["qualifications"][0]["evidence"] = []
            return data

        self.agent.behavior = first_invalid
        self.assertEqual("failed", self.pipeline.process_next()["status"])
        result = self.pipeline.process_next()
        self.assertEqual(str(next_id), result["job_posting_id"])
        self.assertEqual("succeeded", result["status"])
        self.assertTrue(self.exported(next_id).exists())
        self.assertIsNone(self.pipeline.process_next())

    def test_mutating_agent_cannot_replace_the_source_for_evidence_validation(self) -> None:
        original = self.source.get_posting(self.job_id)

        def mutating(posting):
            posting["description_text"] = "private invented responsibility"
            data = analysis_fixture(posting["id"], posting=posting)
            data["qualifications"] = []
            data["compensation"] = []
            data["responsibilities"] = [{
                "value": posting["description_text"],
                "evidence": [{"source_field": "description_text", "quote": posting["description_text"]}],
            }]
            return data

        self.agent.behavior = mutating
        result = self.pipeline.analyze(self.job_id)
        self.assertEqual("failed", result["status"])
        self.assertIn("evidence_quote_not_in_source", result["error_message"])
        self.assertNotIn("private", result["error_message"])
        self.assertFalse(self.exported().exists())
        self.assertEqual(original, self.source.get_posting(self.job_id))

    def test_numeric_boolean_source_evidence_and_dollar_sign_round_trip_unchanged(self) -> None:
        # A fake source extension exercises supported JSON scalar evidence; the
        # source SQL database and production Agent are not used for this input.
        source = self.source.get_posting(self.job_id)
        source["salary_min"] = 100000
        source["relocation_supported"] = True
        expected = analysis_fixture(self.job_id, posting=source)
        expected["compensation"][0]["evidence"].append({
            "source_field": "salary_min", "quote": "100000",
        })
        expected["job_conditions"] = [{
            "type": "other",
            "value": "Relocation is supported.",
            "evidence": [{"source_field": "relocation_supported", "quote": "true"}],
        }]
        self.agent.behavior = lambda _posting: deepcopy(expected)
        with patch.object(self.source, "get_posting", return_value=source):
            result = self.pipeline.analyze(self.job_id)
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(28, len(result["structured_data"]))
        self.assertEqual(expected, result["structured_data"])
        self.assertEqual(expected, json.loads(self.exported().read_text(encoding="utf-8")))
        self.assertIn("$100,000", self.exported().read_text(encoding="utf-8"))
        self.assertNotIn(chr(92) + "$", self.exported().read_text(encoding="utf-8"))

    def test_deleted_queued_source_fails_without_blocking_other_work(self) -> None:
        self.pipeline.enqueue(self.job_id)
        next_id = self.add_posting("still-present")
        self.pipeline.enqueue(next_id)
        with self.session_factory() as session, session.begin():
            session.delete(session.get(JobPosting, self.job_id))
        failed = self.pipeline.process_next()
        self.assertEqual(str(self.job_id), failed["job_posting_id"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual([], self.agent.calls)
        succeeded = self.pipeline.process_next()
        self.assertEqual(str(next_id), succeeded["job_posting_id"])
        self.assertEqual("succeeded", succeeded["status"])
        self.assertEqual(1, len(self.agent.calls))

    def test_failed_local_export_propagates_and_preserves_previous_success(self) -> None:
        previous = self.pipeline.analyze(self.job_id)["structured_data"]
        previous_file = self.exported().read_bytes()
        updated = analysis_fixture(self.job_id, posting=self.source.get_posting(self.job_id), include_overview=True)
        self.agent.behavior = lambda _posting: deepcopy(updated)

        with patch.object(self.store, "_write_result", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.pipeline.analyze(self.job_id, force=True)

        saved = self.store.get(str(self.job_id))
        self.assertEqual("running", saved["status"])
        self.assertEqual(previous, saved["structured_data"])
        self.assertNotEqual(updated, saved["structured_data"])
        self.assertEqual(previous_file, self.exported().read_bytes())
        self.assertEqual(previous, json.loads(self.exported().read_text(encoding="utf-8")))
        self.assertEqual(2, len(self.agent.calls))

    def test_graceful_interrupt_requeues_only_owned_attempt_and_preserves_result(self) -> None:
        original = self.pipeline.analyze(self.job_id)["structured_data"]
        original_file = self.exported().read_bytes()
        for interruption in (KeyboardInterrupt, SystemExit):
            with self.subTest(interruption=interruption.__name__):
                def interrupt(_posting):
                    raise interruption()

                self.agent.behavior = interrupt
                with self.assertRaises(interruption):
                    self.pipeline.analyze(self.job_id, force=True)
                saved = self.store.get(str(self.job_id))
                self.assertEqual("queued", saved["status"])
                self.assertEqual(original, saved["structured_data"])
                self.assertEqual(original_file, self.exported().read_bytes())
                self.agent.behavior = None
                self.assertEqual("succeeded", self.pipeline.process_next()["status"])

    def test_cleanup_error_does_not_mask_original_interrupt(self) -> None:
        self.agent.behavior = lambda _posting: (_ for _ in ()).throw(KeyboardInterrupt())
        with patch.object(self.store, "release", side_effect=OSError("private path")):
            with self.assertRaises(KeyboardInterrupt):
                self.pipeline.analyze(self.job_id)
        self.assertEqual("running", self.store.get(str(self.job_id))["status"])

    def test_restarted_pipeline_recovers_expired_attempt_and_keeps_source_read_only(self) -> None:
        clock = [1000.0]
        store = LocalJobAnalysisStore(self.directory, clock=lambda: clock[0])
        self.pipeline.enqueue(self.job_id)
        old_attempt = store.claim(str(self.job_id))
        clock[0] += 121
        restarted = JobPostingAnalysisPipeline(
            self.source, LocalJobAnalysisStore(self.directory, clock=lambda: clock[0]), self.agent
        )
        self.record_sql = True
        self.assertEqual(1, restarted.recover_interrupted())
        self.assertEqual([], self.source_sql)
        self.assertEqual(0, restarted.recover_interrupted())
        result = restarted.process_next()
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(28, len(result["structured_data"]))
        self.assertEqual(1, len(self.agent.calls))
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in self.source_sql))
        with self.assertRaises(LocalAnalysisStateError):
            store.finish(str(self.job_id), old_attempt, data=analysis_fixture(self.job_id))

    def test_late_agent_result_cannot_overwrite_recovered_attempt(self) -> None:
        previous = self.pipeline.analyze(self.job_id)["structured_data"]
        previous_file = self.exported().read_bytes()
        clock = [1000.0]
        store = LocalJobAnalysisStore(self.directory, clock=lambda: clock[0])
        pipeline = JobPostingAnalysisPipeline(self.source, store, self.agent)
        successor = []

        def delayed_result(posting):
            clock[0] += 121
            self.assertEqual(1, store.recover_interrupted())
            successor.append(store.claim(posting["id"]))
            return analysis_fixture(posting["id"], posting=posting, include_overview=True)

        self.agent.behavior = delayed_result
        with self.assertRaises(LocalAnalysisStateError):
            pipeline.analyze(self.job_id, force=True)
        self.assertEqual("running", store.get(str(self.job_id))["status"])
        self.assertEqual(previous, store.get(str(self.job_id))["structured_data"])
        self.assertEqual(previous_file, self.exported().read_bytes())
        new = analysis_fixture(self.job_id, posting=self.source.get_posting(self.job_id), include_overview=True)
        self.assertEqual("succeeded", store.finish(str(self.job_id), successor[0], data=new)["status"])
        self.assertEqual(new, json.loads(self.exported().read_text(encoding="utf-8")))

    def test_live_heartbeat_protects_a_long_agent_call_from_recovery(self) -> None:
        clock = [1000.0]
        store = LocalJobAnalysisStore(self.directory, lease_seconds=0.12, clock=lambda: clock[0])
        competitor = LocalJobAnalysisStore(self.directory, lease_seconds=0.12, clock=lambda: clock[0])
        pipeline = JobPostingAnalysisPipeline(self.source, store, self.agent)
        renewed = threading.Event()
        original_renew = store.renew
        clock_lock = threading.Lock()

        def renew(*args):
            with clock_lock:
                result = original_renew(*args)
                if result:
                    renewed.set()
                return result

        def long_call(posting):
            for _ in range(3):
                with clock_lock:
                    renewed.clear()
                    clock[0] += 0.08
                self.assertTrue(renewed.wait(timeout=2))
                self.assertEqual(0, competitor.recover_interrupted())
                self.assertEqual("running", competitor.get(posting["id"])["status"])
            return analysis_fixture(posting["id"], posting=posting)

        self.agent.behavior = long_call
        with patch.object(store, "renew", side_effect=renew):
            self.assertEqual("succeeded", pipeline.analyze(self.job_id)["status"])
        self.assertGreater(clock[0] - 1000, 0.12)
        self.assertEqual(1, len(self.agent.calls))

    def test_abrupt_child_process_exit_is_recovered_on_restart(self) -> None:
        # The child has only a fake source and fake Agent. os._exit bypasses all
        # cleanup, matching a killed worker without touching cloud services.
        script = f"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
sys.path.insert(0, {str(BACKEND_ROOT)!r})
from app.services.local_job_analysis_store import LocalJobAnalysisStore
from app.services.job_posting_analysis_pipeline import JobPostingAnalysisPipeline
class Source:
    def get_posting(self, job_id):
        return {{"id": str(job_id)}}
class Agent:
    def analyze(self, posting):
        os._exit(23)
store = LocalJobAnalysisStore(Path({str(self.directory)!r}), clock=lambda: 1000.0)
JobPostingAnalysisPipeline(Source(), store, Agent()).analyze({str(self.job_id)!r})
"""
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(23, result.returncode, result.stderr)
        self.assertEqual("running", self.store.get(str(self.job_id))["status"])
        clock = [1121.0]
        restarted = JobPostingAnalysisPipeline(
            self.source, LocalJobAnalysisStore(self.directory, clock=lambda: clock[0]), self.agent
        )
        self.assertEqual(1, restarted.recover_interrupted())
        self.assertEqual("succeeded", restarted.process_next()["status"])
        self.assertEqual(1, len(self.agent.calls))
        self.assertEqual(28, len(json.loads(self.exported().read_text(encoding="utf-8"))))


# Source restrictions remain covered independently of Agent behavior.
class TrackingSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.was_closed = False

    def close(self):
        self.was_closed = True
        super().close()


class ReadOnlyJobPostingSourceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        # Deliberately create only the source table. JPA and ingest_runs do not exist.
        JobPosting.__table__.create(self.engine)
        self.session_maker = sessionmaker(self.engine, class_=TrackingSession)
        self.sessions = []
        self.source = ReadOnlyJobPostingSource(self.session_factory)
        self.job_id = UUID(int=2)
        self.add_posting(self.job_id)
        self.statements = []
        event.listen(self.engine, "before_cursor_execute", self.record_statement)

    def tearDown(self):
        event.remove(self.engine, "before_cursor_execute", self.record_statement)
        self.engine.dispose()

    def record_statement(self, connection, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    def session_factory(self):
        session = self.session_maker()
        self.sessions.append(session)
        return session

    def add_posting(self, job_id):
        now = datetime(2026, 10, 20, 12, 30, 15, tzinfo=UTC)
        with Session(self.engine) as session:
            session.add(JobPosting(
                id=job_id, source="greenhouse", external_id=str(job_id),
                company_slug="example", company_name="Example", company_tier="other",
                title="Software Engineer", location="Example City", country=None,
                workplace_type=None, department="Engineering", employment_type=None,
                description_text="Python or Go is required.", salary_min=None,
                salary_max=None, salary_currency=None, salary_interval=None,
                url="https://example.test/jobs/1", published_at=now,
                first_seen_at=now, last_seen_at=now, closed_at=None,
                content_hash="0" * 64, created_at=now, updated_at=now,
            ))
            session.commit()

    def test_full_25_fields_are_json_ready_and_nulls_preserved(self):
        result = self.source.get_posting(str(self.job_id))
        self.assertEqual(set(result), set(JobPosting.__table__.columns.keys()))
        self.assertEqual(len(result), 25)
        self.assertEqual(result["id"], str(self.job_id))
        self.assertEqual(result["first_seen_at"], "2026-10-20T12:30:15")
        self.assertIsNone(result["salary_min"])
        self.assertIsNone(result["closed_at"])
        self.assertEqual(json.loads(json.dumps(result)), result)
        self.assertTrue(self.sessions[-1].was_closed)

    def test_invalid_id_fails_before_opening_a_session(self):
        for value in ("", "not-a-uuid", None, 12):
            with self.subTest(value=value), self.assertRaises(JobPostingAnalysisInputError):
                self.source.get_posting(value)
        self.assertEqual(self.sessions, [])

    def test_missing_posting_is_not_found_and_session_is_closed(self):
        with self.assertRaises(JobPostingNotFoundError):
            self.source.get_posting(uuid4())
        self.assertTrue(self.sessions[-1].was_closed)

    def test_keyset_paging_is_unique_ordered_and_closes_before_yield(self):
        for job_id in (UUID(int=5), UUID(int=1), UUID(int=3)):
            self.add_posting(job_id)
        self.statements.clear()
        iterator = self.source.iter_ids(batch_size=1)
        seen = []
        for value in iterator:
            seen.append(value)
            self.assertTrue(all(session.was_closed for session in self.sessions))
        self.assertEqual(seen, [str(UUID(int=n)) for n in (1, 2, 3, 5)])
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in self.statements))
        self.assertTrue(all("job_postings_analyses" not in statement for statement in self.statements))

    def test_id_scan_selects_only_ids_not_descriptions(self):
        self.assertEqual(list(self.source.iter_ids()), [str(self.job_id)])
        self.assertEqual(len(self.statements), 1)
        self.assertNotIn("description_text", self.statements[0])
        self.assertIn("job_postings.id", self.statements[0])

    def test_title_lookup_closes_sessions_and_rejects_invalid_ids_before_read(self):
        self.assertEqual(self.source.get_titles([str(self.job_id)]), {
            str(self.job_id): "Software Engineer",
        })
        self.assertTrue(all(session.was_closed for session in self.sessions))
        self.sessions.clear()
        with self.assertRaises(JobPostingAnalysisInputError):
            self.source.get_titles([str(self.job_id), "invalid"])
        self.assertEqual(self.sessions, [])
        self.assertEqual(self.source.get_titles([]), {})
        self.assertEqual(self.sessions, [])

    def test_empty_source_yields_no_ids(self):
        with Session(self.engine) as session:
            session.query(JobPosting).delete()
            session.commit()
        self.statements.clear()
        self.assertEqual(list(self.source.iter_ids(1)), [])
        self.assertTrue(self.sessions[-1].was_closed)

    def test_invalid_batch_size_fails_before_source_access(self):
        for size in (0, -1, True, "1", 1.5):
            with self.subTest(size=size), self.assertRaises(JobPostingAnalysisInputError):
                list(self.source.iter_ids(size))
        self.assertEqual(self.sessions, [])

    def test_source_executes_selects_without_commit_or_flush(self):
        self.source.get_posting(self.job_id)
        list(self.source.iter_ids())
        self.assertTrue(self.statements)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in self.statements))
        self.assertEqual(inspect(self.engine).get_table_names(), ["job_postings"])

    def test_local_guard_rejects_dml_and_is_removed_for_other_consumers(self):
        with self.source._session() as session:
            with self.assertRaises(JobPostingSourceReadOnlyError):
                session.execute(text("UPDATE job_postings SET title='forbidden'"))
        self.assertEqual(self.source.get_posting(self.job_id)["title"], "Software Engineer")
        # The source hook does not change the engine or the existing scraper.
        with Session(self.engine) as session:
            session.execute(text("UPDATE job_postings SET title='separate consumer'"))
            session.commit()
        self.assertEqual(self.source.get_posting(self.job_id)["title"], "separate consumer")

    def test_postgresql_read_only_is_first_before_select_without_real_connection(self):
        calls = []
        connection = Mock(dialect=SimpleNamespace(name="postgresql"))
        connection.exec_driver_sql.side_effect = lambda sql: calls.append(sql)
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.no_autoflush = nullcontext()
        session.connection.return_value = connection
        session.scalars.side_effect = lambda query: calls.append(str(query)) or []
        source = ReadOnlyJobPostingSource(lambda: session)
        with patch("app.services.job_posting_analysis_pipeline.event.listen") as listen, patch(
            "app.services.job_posting_analysis_pipeline.event.remove"
        ) as remove:
            self.assertEqual(list(source.iter_ids()), [])
        self.assertEqual(calls[0], "SET TRANSACTION READ ONLY")
        self.assertTrue(calls[1].startswith("SELECT job_postings.id"))
        listen.assert_called_once()
        remove.assert_called_once()
        session.commit.assert_not_called()

    def test_read_only_setup_failure_does_not_run_a_source_query(self):
        connection = Mock(dialect=SimpleNamespace(name="postgresql"))
        connection.exec_driver_sql.side_effect = RuntimeError("read-only setup failed")
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.no_autoflush = nullcontext()
        session.connection.return_value = connection
        source = ReadOnlyJobPostingSource(lambda: session)
        with self.assertRaisesRegex(RuntimeError, "read-only setup failed"):
            source.get_posting(self.job_id)
        session.scalar.assert_not_called()
        session.commit.assert_not_called()

    def test_guard_rejects_textual_multi_statement_before_execution(self):
        with self.source._session() as session:
            with self.assertRaises(JobPostingSourceReadOnlyError):
                session.execute(text("SELECT id FROM job_postings; DELETE FROM job_postings"))
        self.assertEqual(self.source.get_posting(self.job_id)["title"], "Software Engineer")


# The future cloud destination stays explicitly disabled.
class SupabaseAnalysisPersistencePlaceholderTests(unittest.TestCase):
    def test_disabled_save_preserves_payload_and_never_exposes_private_input(self) -> None:
        payload = agent_analysis_fixture()
        private_note = "PRIVATE compensation note: $123,456"
        payload["compensation"][0]["value"] = private_note
        original = deepcopy(payload)
        job_id = agent_posting_fixture()["id"]
        self.assertEqual(28, len(payload))
        with self.assertRaises(SupabaseAnalysisPersistenceNotEnabled) as caught:
            save_analysis_to_supabase(job_posting_id=job_id, structured_data=payload)
        self.assertEqual(
            "Supabase analysis persistence is not enabled; keep results in local storage.",
            str(caught.exception),
        )
        self.assertNotIn(private_note, str(caught.exception))
        self.assertNotIn(job_id, str(caught.exception))
        self.assertEqual(original, payload)
        # Invalid, non-serializable input must still refuse instead of attempting a write.
        with self.assertRaises(SupabaseAnalysisPersistenceNotEnabled):
            save_analysis_to_supabase(
                job_posting_id="invalid-id", structured_data={"private": object()}
            )

    def test_import_and_refusal_need_no_database_or_azure_configuration(self) -> None:
        script = r'''
import sys
sys.dont_write_bytecode = True

import builtins
import socket
import sqlite3
from pathlib import Path
from unittest.mock import patch

import sqlalchemy
from sqlalchemy.engine import Engine

sys.path.insert(0, sys.argv[1])
original_import = builtins.__import__
original_open = builtins.open
original_path_open = Path.open

def guarded_import(name, *args, **kwargs):
    # The merged pipeline may import SQLAlchemy models, but must not load cloud
    # SDKs, runtime credentials/settings, or the configured database session.
    if (name.split(".")[0] in {"azure", "openai"}
            or name == "app.db.session" or name == "app.core.config"):
        raise AssertionError("A disabled destination must not load configuration or cloud clients.")
    return original_import(name, *args, **kwargs)

def guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in "wax+"):
        raise AssertionError("Importing or refusing a save must not write files.")
    return original_open(file, mode, *args, **kwargs)

def guarded_path_open(path, mode="r", *args, **kwargs):
    if any(flag in mode for flag in "wax+"):
        raise AssertionError("Importing or refusing a save must not write files.")
    return original_path_open(path, mode, *args, **kwargs)

builtins.__import__ = guarded_import
with (
    patch("builtins.open", guarded_open),
    patch.object(Path, "open", guarded_path_open),
    patch.object(sqlalchemy, "create_engine", side_effect=AssertionError("No engine construction.")),
    patch.object(Engine, "connect", side_effect=AssertionError("No database connection.")),
    patch.object(sqlite3, "connect", side_effect=AssertionError("No local database connection.")),
    patch.object(socket, "create_connection", side_effect=AssertionError("No network connection.")),
    patch.object(socket.socket, "connect", side_effect=AssertionError("No network connection.")),
    patch.object(Path, "mkdir", side_effect=AssertionError("No output directory creation.")),
):
    from app.services.job_posting_analysis_pipeline import (
        SupabaseAnalysisPersistenceNotEnabled, save_analysis_to_supabase,
    )
    marker = object()
    payload = {"private": marker}
    try:
        save_analysis_to_supabase(job_posting_id="unused", structured_data=payload)
    except SupabaseAnalysisPersistenceNotEnabled:
        assert payload == {"private": marker}
        print("disabled without database or Azure configuration")
    else:
        raise AssertionError("The future destination must refuse saves.")
'''
        completed = subprocess.run(
            [sys.executable, "-I", "-c", script, str(BACKEND_ROOT)],
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            "disabled without database or Azure configuration",
            completed.stdout.strip(),
        )

    def test_active_pipeline_saves_locally_without_calling_remote_placeholder(self) -> None:
        posting = agent_posting_fixture()
        expected = agent_analysis_fixture()
        source = Mock()
        source.get_posting.return_value = deepcopy(posting)
        agent = Mock()
        agent.analyze.return_value = deepcopy(expected)
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalJobAnalysisStore(Path(temporary))
            pipeline = JobPostingAnalysisPipeline(source, store, agent)
            with patch(
                "app.services.job_posting_analysis_pipeline.save_analysis_to_supabase",
                side_effect=AssertionError("Remote persistence must not be called."),
            ) as remote_save:
                result = pipeline.analyze(posting["id"])
                cached = pipeline.analyze(posting["id"])
            self.assertEqual("succeeded", result["status"])
            self.assertEqual(expected, result["structured_data"])
            self.assertEqual(result, cached)
            saved = json.loads(
                (Path(temporary) / "results" / f"{posting['id']}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(expected, saved)
            self.assertEqual(28, len(saved))
            agent.analyze.assert_called_once_with(posting)
            remote_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
