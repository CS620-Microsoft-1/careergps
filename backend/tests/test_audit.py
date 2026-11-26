"""The audit log: what each write records, where the record goes, and that every write method records."""
import inspect
import re
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from app.core.config import BACKEND_ROOT
from app.models.audit_log import AuditLog
from app.services import accounts, agent_calls, audit, plans, student_courses
from app.services.postings import ingest
from app.services.skill_gaps import run_store
from scripts import backfill_resume_children, seed_catalog

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")


class FailingWriter:
    def write(self, row):
        raise ConnectionError("database down")


class RecordTests(unittest.TestCase):
    def test_record_adds_a_row_to_the_callers_session(self) -> None:
        session = MagicMock()
        audit.record(session, "course.marked_taken", user_id=str(USER), target=("school_course", "uw-cs-400"),
                     details={"source": "manual"})
        [row] = [call.args[0] for call in session.add.call_args_list]
        self.assertIsInstance(row, AuditLog)
        self.assertEqual((USER, "course.marked_taken", "school_course", "uw-cs-400", {"source": "manual"}, "script"),
                         (row.user_id, row.action, row.target_type, row.target_id, row.details, row.source))
        session.commit.assert_not_called()

    def test_inside_a_request_the_source_is_api_and_the_user_comes_from_context(self) -> None:
        token = agent_calls.start_request()
        self.addCleanup(agent_calls.end_request, token)
        agent_calls.set_user(USER)
        session = MagicMock()
        audit.record(session, "account.updated")
        row = session.add.call_args.args[0]
        self.assertEqual((USER, "api", {}, None, None), (row.user_id, row.source, row.details, row.target_type,
                                                          row.target_id))

    def test_an_explicit_user_wins_over_context(self) -> None:
        token = agent_calls.start_request()
        self.addCleanup(agent_calls.end_request, token)
        agent_calls.set_user(uuid.uuid4())
        session = MagicMock()
        audit.record(session, "skill_gap.run_created", user_id=USER)
        self.assertEqual(USER, session.add.call_args.args[0].user_id)

    def test_shared_data_has_no_user(self) -> None:
        session = MagicMock()
        audit.record(session, "catalog.seeded", details={"certifications": {"inserted": 3}})
        self.assertIsNone(session.add.call_args.args[0].user_id)


class DetachedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = audit.MemoryWriter()
        audit.use_writer(self.writer)
        self.addCleanup(audit.use_writer, audit.MemoryWriter())

    def test_a_failed_write_is_logged_not_raised(self) -> None:
        audit.use_writer(FailingWriter())
        with self.assertLogs("app.services.audit", "WARNING") as logs:
            audit.record_detached("plan.item_saved", user_id=USER)
        self.assertNotIn("database down", "".join(logs.output))

    def test_plan_writes_record_saves_and_real_removals_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = plans.LocalPlanStore(Path(directory))
            store.set_status(USER, "data_analyst", "uw-cs-400", "saved")
            store.set_status(USER, "data_analyst", "uw-cs-400", "done")
            store.remove(USER, "data_analyst", "uw-cs-400")
            store.remove(USER, "data_analyst", "uw-cs-400")  # nothing left to remove
        self.assertEqual([("plan.item_saved", {"job_family": "data_analyst", "status": "saved"}),
                          ("plan.item_saved", {"job_family": "data_analyst", "status": "done"}),
                          ("plan.item_removed", {"job_family": "data_analyst"})],
                         [(row["action"], row["details"]) for row in self.writer.rows])
        self.assertEqual({USER}, {row["user_id"] for row in self.writer.rows})
        self.assertEqual({("resource", "uw-cs-400")}, {(row["target_type"], row["target_id"]) for row in self.writer.rows})


class AccountServiceTests(unittest.TestCase):
    """The real AccountService methods, with a mock session: each adds its audit row before committing."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = accounts.AccountService(self.db)
        self.user = accounts.User(id=USER, primary_email="ada@example.com")

    def added(self) -> list[AuditLog]:
        return [call.args[0] for call in self.db.add.call_args_list if isinstance(call.args[0], AuditLog)]

    def test_update_records_changed_field_names_not_values(self) -> None:
        data = accounts.AccountUpdate.model_validate({"first_name": "Grace", "university": "UW-Madison"})
        self.service.update_account(self.user, data)
        [row] = self.added()
        self.assertEqual(("account.updated", {"fields": ["first_name", "university"]}), (row.action, row.details))
        self.assertNotIn("Grace", repr(row.details))
        self.db.commit.assert_called_once_with()

    def test_email_sync_records_only_a_real_change(self) -> None:
        self.service.sync_email(self.user, "ADA@example.com")
        self.assertEqual([], self.added())
        self.service.sync_email(self.user, "ada@new.example.com")
        [row] = self.added()
        self.assertEqual(("account.email_synced", {"fields": ["primary_email"]}), (row.action, row.details))


class CoursesTests(unittest.TestCase):
    def test_unmark_records_only_when_a_row_was_removed(self) -> None:
        session = MagicMock()
        session.get.return_value = None
        student_courses.unmark_taken(session, USER, "uw-cs-400")
        session.add.assert_not_called()
        session.get.return_value = object()
        student_courses.unmark_taken(session, USER, "uw-cs-400")
        self.assertEqual("course.unmarked_taken", session.add.call_args.args[0].action)


# Every method that writes the database or the plan files, and the reason the others need no record.
RECORDING = {
    accounts.AccountService.create_account, accounts.AccountService.update_account,
    accounts.AccountService.add_resume, accounts.AccountService.use_resume, accounts.AccountService.sync_email,
    student_courses.mark_taken, student_courses.unmark_taken,
    plans.LocalPlanStore.set_status, plans.LocalPlanStore.remove,
    run_store.DbRunStore.create, run_store.DbRunStore.complete,
    ingest.ingest, seed_catalog.seed, backfill_resume_children.backfill,
}
NOT_RECORDING = {
    "AccountService.end_reads": "commits a read-only transaction",
    "AccountService._point": "callers (add_resume, use_resume, create_account) record before it commits",
    "record_done_course": "calls mark_taken",
    "DbRunStore.save_state": "run progress; creation and completion are recorded",
    "JsonRunStore.save_state": "local run files for development; the API uses DbRunStore",
    "DatabaseSink.write": "writes agent_calls itself",
    "DatabaseWriter.write": "writes audit_log itself",
    "main": "a script's entry point; the function it calls records",
}
_WRITES = re.compile(r"\.commit\(\)|session\.begin\(\)|save_json\(")


class CoverageTests(unittest.TestCase):
    def test_listed_write_methods_record(self) -> None:
        for method in RECORDING:
            source = inspect.getsource(method)
            self.assertRegex(source, r"audit\.record(_detached)?\(", method.__qualname__)

    def test_every_database_or_plan_write_is_listed(self) -> None:
        """A new method that commits must record (and be added to RECORDING) or say why not."""
        listed = {method.__qualname__ for method in RECORDING} | set(NOT_RECORDING)
        files = [BACKEND_ROOT / "app/services/accounts.py", BACKEND_ROOT / "app/services/student_courses.py",
                 BACKEND_ROOT / "app/services/plans.py", BACKEND_ROOT / "app/services/skill_gaps/run_store.py",
                 BACKEND_ROOT / "app/services/postings/ingest.py", BACKEND_ROOT / "app/services/agent_calls.py",
                 BACKEND_ROOT / "app/services/audit.py", *sorted((BACKEND_ROOT / "scripts").glob("*.py"))]
        unlisted = []
        for path in files:
            for name, body in _functions(path.read_text(encoding="utf-8")):
                if _WRITES.search(body) and name not in listed:
                    unlisted.append(f"{path.relative_to(BACKEND_ROOT)}: {name}")
        self.assertEqual([], unlisted)

    def test_writes_in_other_services_are_known(self) -> None:
        """Services not checked above must not commit, except the local job analysis store (SQLite)."""
        checked = {"accounts.py", "student_courses.py", "plans.py", "run_store.py", "ingest.py", "agent_calls.py",
                   "audit.py", "local_job_analysis_store.py"}
        committing = [str(path.relative_to(BACKEND_ROOT)) for path in (BACKEND_ROOT / "app").rglob("*.py")
                      if path.name not in checked and re.search(r"\.commit\(\)|session\.begin\(\)",
                                                                path.read_text(encoding="utf-8"))]
        self.assertEqual([], committing)


def _functions(source: str):
    """(qualified name, body) for each def, by indentation; enough for these files."""
    lines = source.splitlines()
    stack: list[tuple[int, str]] = []
    starts = []
    for number, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:class|def)\s+(\w+)", line)
        if match:
            indent = len(match.group(1))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, match.group(2)))
            if line.lstrip().startswith("def"):
                starts.append((number, indent, ".".join(name for _, name in stack)))
    for index, (number, indent, name) in enumerate(starts):
        end = len(lines)
        for later in range(number + 1, len(lines)):
            stripped = lines[later]
            if stripped.strip() and len(stripped) - len(stripped.lstrip()) <= indent:
                end = later
                break
        yield name, "\n".join(lines[number:end])


if __name__ == "__main__":
    unittest.main()
