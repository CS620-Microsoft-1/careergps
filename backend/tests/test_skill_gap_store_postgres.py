"""DbRunStore against a real, throwaway Postgres with the real migrations. Synthetic data only.

Skipped unless TEST_DATABASE_URL is set, so CI (no database) skips it. Never point it at the shared
Supabase database: it drops and recreates the public and auth schemas. For example:

    docker run --rm -d --name careergps-test-db -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17
    TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres python -m unittest tests.test_skill_gap_store_postgres
    docker stop careergps-test-db
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL or "postgresql+psycopg://x:y@localhost:5432/test")

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.skill_gap import SkillGapResult, SkillGapRunBranch, SkillGapRunRecord
from app.services.skill_gaps.match import summarize_match
from app.services.skill_gaps.persistence import STORAGE_SCHEMA_VERSION
from app.services.skill_gaps.run_store import ActiveRunExists, DbRunStore
from tempfile import TemporaryDirectory

from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, group_manager, reviewed_resume
# The module, not the class: importing a TestCase class here would run its tests twice.
from tests import test_skill_gap_persistence as persistence_tests
from tests.test_skill_gap_run_ownership import wait_for

CONTRACTS = BACKEND_ROOT.parent / "docs" / "contracts"
EXAMPLE = json.loads((CONTRACTS / "skill-gap-run-storage-v3.example.json").read_text(encoding="utf-8"))
RUN_FIELDS = {"demand_snapshot_fingerprint": "d" * 64, "catalog_version": "core-cards.v1",
              "partition_policy_version": "core-skill-partitions.v1",
              "selection_policy_version": "sole-owner-whole-record-assembly.v1"}
GROUPS = ("foundation", "lifecycle", "systems")


class _PostgresCase(unittest.TestCase):
    """Throwaway database with every migration, a fresh user and résumé per test, and the helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        if "supabase" in TEST_DATABASE_URL:
            raise RuntimeError("TEST_DATABASE_URL points at Supabase; use a throwaway database")
        cls.engine = create_engine(TEST_DATABASE_URL)
        with cls.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public"))
            connection.execute(text("DROP SCHEMA IF EXISTS auth CASCADE; CREATE SCHEMA auth"))
            connection.execute(text("CREATE TABLE auth.users (id uuid PRIMARY KEY, "
                                    "created_at timestamptz NOT NULL DEFAULT now(), email_confirmed_at timestamptz)"))
        # Both URLs: Alembic prefers MIGRATION_DATABASE_URL, which a developer's .env may point at Supabase.
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, check=True,
                       capture_output=True, env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL,
                                                 "MIGRATION_DATABASE_URL": TEST_DATABASE_URL})
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.user_id, self.resume_id = self.ids()
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE users, auth.users CASCADE"))
            connection.execute(text("INSERT INTO auth.users (id, email_confirmed_at) VALUES (:id, now())"),
                               {"id": self.user_id})
            connection.execute(text(
                "INSERT INTO users (id, primary_email, first_name, last_name, university, graduation_year, "
                "experience_level, target_role, preferred_location, terms_accepted_at) VALUES (:id, "
                "'alex@example.invalid', 'Alex', 'Example', 'Example University', 2027, 'Internship', "
                "'Software Engineer', 'Madison', now())"), {"id": self.user_id})
            connection.execute(text(
                "INSERT INTO resumes (id, user_id, original_filename, file_type, parser, agent_name, schema_version, "
                "confirmed_data) VALUES (:id, :user, 'alex-example.pdf', 'pdf', 'pymupdf', 'fixture', 'v1', '{}')"),
                {"id": self.resume_id, "user": self.user_id})
        self.store = DbRunStore(self.Session)

    # -- helpers ----------------------------------------------------------------------------------

    def ids(self):
        return uuid4(), uuid4()

    def state(self, **changes) -> dict:
        value = {"id": uuid4().hex, "user_id": str(self.user_id), "resume_id": str(self.resume_id),
                 "job_family": "software_engineer", "resume_hash": "a" * 64, "status": "queued", "phase": "queued",
                 "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
                 "elapsed_seconds": 0.0, "model_calls": 0, "error": None, "filename": "alex-example.pdf",
                 "confirmed_at": CONFIRMED_AT.isoformat(), "calculation_fingerprint": "b" * 64,
                 "prompt_revision": "skill-groups.v1", "instructions_sha256": "c" * 64,
                 "response_processing_version": "rp.v1", "extraction_strategy": "skill_groups",
                 "reuse_from_run_id": None}
        value.update(changes)
        return value

    def running(self, state: dict, **branch_changes) -> dict:
        state.update(status="running", phase="agent", model_calls=3)
        state["branches"] = {group: {"status": "running", "agent_name": f"fixture-{group}", "agent_version": "1",
                                     "model_calls": 1, "elapsed_seconds": 0.5, "reused": False, "error_code": None,
                                     **branch_changes} for group in GROUPS}
        return state

    def finished(self, state: dict) -> dict:
        for branch in state["branches"].values():
            branch.update(status="completed", elapsed_seconds=1.5)
        state.update(status="completed", phase="completed", completed_at=datetime.now(timezone.utc).isoformat(),
                     elapsed_seconds=3.0, azure_phase_timings={"branches": {"foundation": {"inference_seconds": 1.2}}})
        return state

    def branch_details(self) -> dict:
        details = {}
        for group in GROUPS:
            node = EXAMPLE["branches"][group]
            details[group] = {
                "payload": {"group": group}, "output": node["raw_output"], "validation": node["validation"],
                "response_processing": node["response_processing"], "timings": {"inference_seconds": 0.9},
                "raw_response": {"model": "fixture-model", "reasoning": {"effort": "medium"},
                                 "usage": {"input_tokens": 6900, "input_tokens_details": {"cached_tokens": 3200},
                                           "output_tokens": 2600, "output_tokens_details": {"reasoning_tokens": 1900}}}}
        return details

    def complete(self, state: dict, report: dict | None = None) -> None:
        self.store.complete(state, report=report or EXAMPLE["report"], extraction_audit=EXAMPLE["extraction_audit"],
                            merged_output=EXAMPLE["raw_agent_output"], branches=self.branch_details())

    def count(self, model, run_id: str) -> int:
        column = model.id if model is SkillGapRunRecord else model.run_id
        with self.Session() as session:
            return session.scalar(select(func.count()).select_from(model).where(column == UUID(run_id)))

    def run_row(self, run_id: str) -> SkillGapRunRecord:
        with self.Session() as session:
            return session.get(SkillGapRunRecord, UUID(run_id))



@unittest.skipUnless(TEST_DATABASE_URL, "set TEST_DATABASE_URL to a throwaway Postgres to run")
class DbRunStorePostgresTests(_PostgresCase):

    def test_a_queued_run_keeps_its_snapshot_and_versions(self):
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        row = self.run_row(state["id"])
        self.assertEqual(("queued", STORAGE_SCHEMA_VERSION, "alex-example.pdf", "skill_groups"),
                         (row.status, row.storage_schema_version, row.resume_filename, row.extraction_strategy))
        self.assertEqual(reviewed_resume(), row.reviewed_resume_snapshot)
        self.assertEqual(("d" * 64, "core-cards.v1"), (row.demand_snapshot_fingerprint, row.catalog_version))
        self.assertIsNone(row.report)
        [loaded] = self.store.load_states()
        self.assertEqual(state["id"], loaded["id"])
        for key in ("user_id", "resume_id", "status", "phase", "job_family", "filename", "resume_hash",
                    "calculation_fingerprint", "confirmed_at", "model_calls", "error"):
            self.assertEqual(state[key], loaded[key], key)
        self.assertEqual(datetime.fromisoformat(state["created_at"]), datetime.fromisoformat(loaded["created_at"]))

    def test_only_one_queued_or_running_run_per_resume_role_and_configuration(self):
        first = self.state()
        self.store.create(first, reviewed_resume(), **RUN_FIELDS)
        with self.assertRaises(ActiveRunExists):
            self.store.create(self.state(), reviewed_resume(), **RUN_FIELDS)
        # Another configuration (fingerprint) or a finished first run may start a new one.
        self.store.create(self.state(calculation_fingerprint="e" * 64), reviewed_resume(), **RUN_FIELDS)
        self.store.save_state({**first, "status": "failed", "phase": "failed", "error": "stopped",
                               "error_code": "analysis_failed", "completed_at": datetime.now(timezone.utc).isoformat()})
        self.store.create(self.state(), reviewed_resume(), **RUN_FIELDS)

    def test_progress_updates_the_run_and_its_three_branches(self):
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        self.store.save_state(self.running(state))
        self.assertEqual(("running", "agent", 3), (lambda r: (r.status, r.phase, r.model_calls))(self.run_row(state["id"])))
        self.assertEqual(3, self.count(SkillGapRunBranch, state["id"]))
        state["branches"]["systems"].update(status="failed", error_code="branch_analysis_failed")
        state.update(status="failed", phase="failed", error="The systems Agent could not finish.",
                     error_code="branch_analysis_failed", completed_at=datetime.now(timezone.utc).isoformat())
        self.store.save_state(state)
        [loaded] = self.store.load_states()
        self.assertEqual(("failed", "branch_analysis_failed"), (loaded["status"], loaded["error_code"]))
        self.assertEqual(("failed", "branch_analysis_failed"),
                         (loaded["branches"]["systems"]["status"], loaded["branches"]["systems"]["error_code"]))
        self.assertEqual(3, self.count(SkillGapRunBranch, state["id"]))  # upserted, not duplicated

    def test_completion_writes_the_report_branches_and_one_row_per_skill(self):
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        self.store.save_state(self.running(state))
        self.complete(self.finished(state))
        row = self.run_row(state["id"])
        self.assertEqual(("completed", EXAMPLE["report"]), (row.status, row.report))
        self.assertEqual(round(summarize_match(EXAMPLE["report"])["score"], 4), float(row.match_score))
        self.assertEqual((21, 1), (row.scored_skill_count, row.unscored_skill_count))
        self.assertEqual(EXAMPLE["extraction_audit"], row.extraction_audit)
        self.assertEqual(EXAMPLE["report"], self.store.load_report(state["id"]))
        with self.Session() as session:
            branches = {b.branch: b for b in session.scalars(select(SkillGapRunBranch).where(
                SkillGapRunBranch.run_id == UUID(state["id"])))}
            results = session.scalars(select(SkillGapResult).where(SkillGapResult.run_id == UUID(state["id"]))
                                      .order_by(SkillGapResult.position)).all()
        self.assertEqual(set(GROUPS), set(branches))
        foundation = branches["foundation"]
        self.assertEqual(("completed", "fixture-model", "medium", 6900, 1900),
                         (foundation.status, foundation.model, foundation.reasoning_effort,
                          foundation.input_tokens, foundation.reasoning_tokens))
        self.assertEqual(EXAMPLE["branches"]["foundation"]["raw_output"], foundation.raw_output)
        self.assertEqual([s["skill_id"] for s in EXAMPLE["report"]["skills"]], [r.skill_id for r in results])
        programming = next(r for r in results if r.skill_id == "programming")
        self.assertEqual(["capability", "method", "check"], [item["role"] for item in programming.evidence])
        pending = next(r for r in results if r.calculation_state == "needs_confirmation")
        self.assertEqual((None, None, None), (pending.grade, pending.priority, pending.priority_rank))
        self.assertIsNotNone(pending.merge_audit)

    def test_a_failed_completion_changes_nothing(self):
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        self.store.save_state(self.running(state))
        broken = deepcopy(EXAMPLE["report"])
        scored = next(row for row in broken["skills"] if row["calculation_state"] == "scored")
        scored["skill_gap_grade"] = None  # breaks ck_skill_gap_results_scored_values
        with self.assertRaises(IntegrityError):
            self.complete(self.finished(state), report=broken)
        row = self.run_row(state["id"])
        self.assertEqual(("running", None, None), (row.status, row.report, row.match_score))
        self.assertEqual(0, self.count(SkillGapResult, state["id"]))
        with self.Session() as session:
            self.assertIsNone(session.get(SkillGapRunBranch, (UUID(state["id"]), "foundation")).raw_output)

    def test_links_to_runs_only_in_old_local_files_are_left_empty(self):
        earlier = self.state()
        self.store.create(earlier, reviewed_resume(), **RUN_FIELDS)
        self.store.save_state({**earlier, "status": "failed", "phase": "failed", "error": "stopped",
                               "error_code": "analysis_failed", "completed_at": datetime.now(timezone.utc).isoformat()})
        retry = self.state(reuse_from_run_id=earlier["id"])
        self.store.create(retry, reviewed_resume(), **RUN_FIELDS)
        self.running(retry, reused=True, model_calls=0)
        retry["branches"]["foundation"]["source_run_id"] = earlier["id"]
        retry["branches"]["lifecycle"]["source_run_id"] = uuid4().hex  # a local-only run
        self.store.save_state(retry)
        with self.Session() as session:
            links = dict(session.execute(select(SkillGapRunBranch.branch, SkillGapRunBranch.source_run_id).where(
                SkillGapRunBranch.run_id == UUID(retry["id"]))).all())
        self.assertEqual(UUID(earlier["id"]), links["foundation"])
        self.assertIsNone(links["lifecycle"])
        self.assertEqual(UUID(earlier["id"]), self.run_row(retry["id"]).reuse_from_run_id)
        orphan = self.state(calculation_fingerprint="f" * 64, reuse_from_run_id=uuid4().hex)
        self.store.create(orphan, reviewed_resume(), **RUN_FIELDS)
        self.assertIsNone(self.run_row(orphan["id"]).reuse_from_run_id)

    def test_every_run_is_kept_and_deleting_the_resume_deletes_them(self):
        ids = []
        for offset in (2, 1):
            state = self.state(created_at=(datetime.now(timezone.utc) - timedelta(minutes=offset)).isoformat())
            self.store.create(state, reviewed_resume(), **RUN_FIELDS)
            self.store.save_state(self.running(state))
            self.complete(self.finished(state))
            ids.append(state["id"])
        self.assertEqual(ids, [s["id"] for s in self.store.load_states()])  # oldest first, both kept
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM resumes WHERE id = :id"), {"id": self.resume_id})
        for run_id in ids:
            for model in (SkillGapRunRecord, SkillGapRunBranch, SkillGapResult):
                self.assertEqual(0, self.count(model, run_id))

    def test_a_skipped_branch_stores_sql_nulls_not_json_nulls(self):
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        self.finished(self.running(state))
        state["branches"]["systems"].update(status="skipped_empty", model_calls=0, agent_version=None)
        details = self.branch_details()
        details["systems"] = {}  # no Agent request: no payload, answer, response or checks
        self.store.complete(state, report=EXAMPLE["report"], extraction_audit=EXAMPLE["extraction_audit"],
                            merged_output=EXAMPLE["raw_agent_output"], branches=details)
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT raw_output IS NULL, validation IS NULL, response_processing IS NULL, input_sha256 IS NULL "
                "FROM skill_gap_run_branches WHERE run_id = :id AND branch = 'systems'"), {"id": UUID(state["id"])}).one()
            originals = connection.execute(text(
                "SELECT count(*) FROM skill_gap_results WHERE run_id = :id AND original_agent_assessment IS NULL"),
                {"id": UUID(state["id"])}).scalar()
        self.assertEqual((True, True, True, True), tuple(row))
        self.assertEqual(len(EXAMPLE["report"]["skills"]), originals)

    def test_a_completed_state_is_only_written_by_complete(self):
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        self.store.save_state(self.finished(self.running(state)))  # no report yet: ignored, not an error
        self.assertEqual("queued", self.run_row(state["id"]).status)

    def test_an_unknown_or_unfinished_run_has_no_report(self):
        with self.assertRaises(KeyError):
            self.store.load_report(uuid4().hex)
        state = self.state()
        self.store.create(state, reviewed_resume(), **RUN_FIELDS)
        with self.assertRaises(KeyError):
            self.store.load_report(state["id"])


@unittest.skipUnless(TEST_DATABASE_URL, "set TEST_DATABASE_URL to a throwaway Postgres to run")
class ManagerWithDbRunStorePostgresTests(_PostgresCase):
    """The real SkillGapRunManager on DbRunStore, with synthetic Agents (no Azure)."""

    def ids(self):
        return USER_ID, RESUME_ID  # the fixtures submit runs for these

    def manager(self, directory):
        manager = group_manager(Path(directory), invoker=persistence_tests.MappingAThreeGroupRunTests.invoke, store=self.store)
        self.addCleanup(manager.close)
        return manager

    def submit(self, manager, **changes):
        options = {"user_id": USER_ID, "resume_id": RESUME_ID, "reviewed_resume": reviewed_resume(),
                   "filename": "alex-example.pdf", "confirmed_at": CONFIRMED_AT, "job_family": "software_engineer"}
        options.update(changes)
        return manager.submit(**options)

    def test_a_completed_run_is_in_the_database_and_survives_a_restart(self):
        with TemporaryDirectory() as directory:
            manager = self.manager(directory)
            run = wait_for(manager, self.submit(manager))
            self.assertEqual("completed", run.status, run.error)
            row = self.run_row(run.id)
            self.assertEqual(("completed", run.report, "alex-example.pdf"), (row.status, row.report, row.resume_filename))
            self.assertEqual(run.match.score if run.match else None, float(row.match_score) if row.match_score is not None else None)
            self.assertEqual(3, self.count(SkillGapRunBranch, run.id))
            self.assertEqual(len(run.report["skills"]), self.count(SkillGapResult, run.id))
            with self.Session() as session:
                programming = session.get(SkillGapResult, (UUID(run.id), "programming"))
            self.assertEqual("Implemented an API in Python", programming.evidence[0]["quote"])

            # A new process (new manager, empty folder) finds the same run in the database.
            with TemporaryDirectory() as other:
                restarted = self.manager(other)
                latest = restarted.latest(user_id=USER_ID, resume_id=RESUME_ID, reviewed_resume=reviewed_resume(),
                                          job_family="software_engineer")
                self.assertEqual((run.id, run.report), (latest.id, latest.report))
                again = self.submit(restarted)
                self.assertEqual((run.id, True), (again.id, again.reused))  # no new paid run

    def test_a_run_interrupted_by_a_crash_fails_on_restart(self):
        with TemporaryDirectory() as directory:
            manager = self.manager(directory)
            state = self.state()
            self.store.create(state, reviewed_resume(), **RUN_FIELDS)
            self.store.save_state(self.running(state))
            with TemporaryDirectory() as other:
                restarted = self.manager(other)
                self.assertEqual("failed", restarted.get(state["id"], user_id=USER_ID).status)
            self.assertEqual(("failed", "failed"), (self.run_row(state["id"]).status, self.run_row(state["id"]).phase))
            manager.close()


if __name__ == "__main__":
    unittest.main()
