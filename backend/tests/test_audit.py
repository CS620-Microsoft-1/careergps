"""The audit log recorder: what a row holds and where it goes."""
import unittest
import uuid
from unittest.mock import MagicMock

from app.models.audit_log import AuditLog
from app.services import agent_calls, audit

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


if __name__ == "__main__":
    unittest.main()
