"""Offline checks for the isolated, authenticated Copilot resume reader.

All database rows are synthetic and live in SQLite memory. These tests never use
an application database, saved report, Azure Agent or a real login token.
"""
from contextlib import nullcontext
from copy import deepcopy
import os
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:fake@127.0.0.1:1/test")

from fastapi import HTTPException
from sqlalchemy import (
    Column, DateTime, Integer, JSON, MetaData, String, Table, Uuid,
    create_engine, delete, event, insert, select, text, update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.models import User
from app.services.copilot import readonly
from app.services.copilot.readonly import CopilotReadOnlyError, ReadOnlyResumeSource, ResumeSnapshot
from tests.skill_gap_fixtures import CONFIRMED_AT, reviewed_resume

USER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
RESUME = UUID("33333333-3333-4333-8333-333333333333")
SECOND = UUID("44444444-4444-4444-8444-444444444444")
FOREIGN = UUID("55555555-5555-4555-8555-555555555555")
MISSING = UUID("66666666-6666-4666-8666-666666666666")


class NoNetwork(unittest.TestCase):
    def setUp(self):
        super().setUp()
        network = patch("socket.socket.connect", side_effect=AssertionError("Offline test attempted network access"))
        network.start()
        self.addCleanup(network.stop)


class ReadOnlyResumeSourceTests(NoNetwork):
    def setUp(self):
        super().setUp()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.users = Table("users", metadata, Column("id", Uuid, primary_key=True))
        self.resumes = Table("resumes", metadata,
            Column("id", Uuid, primary_key=True), Column("user_id", Uuid),
            Column("original_filename", String), Column("confirmed_data", JSON), Column("created_at", DateTime))
        self.destinations = Table("destinations", metadata,
            Column("user_id", Uuid, primary_key=True), Column("job_family", String, primary_key=True),
            Column("resume_id", Uuid))
        metadata.create_all(self.engine)
        self.saved = reviewed_resume()
        self.saved["technical_skills"] = [" Python ", "SQL", "SQL", "TypeScript"]
        second = reviewed_resume()
        second["technical_skills"] = ["Own second direction"]
        foreign = reviewed_resume()
        foreign["technical_skills"] = ["Private foreign skill"]
        with self.engine.begin() as connection:
            connection.execute(insert(self.users), [{"id": USER}, {"id": OTHER}])
            connection.execute(insert(self.resumes), [
                {"id": RESUME, "user_id": USER, "original_filename": "confirmed.pdf",
                 "confirmed_data": self.saved, "created_at": CONFIRMED_AT},
                {"id": SECOND, "user_id": USER, "original_filename": "second.pdf",
                 "confirmed_data": second, "created_at": CONFIRMED_AT},
                {"id": FOREIGN, "user_id": OTHER, "original_filename": "other.pdf",
                 "confirmed_data": foreign, "created_at": CONFIRMED_AT},
            ])
            connection.execute(insert(self.destinations), [
                {"user_id": USER, "job_family": "ai_engineer", "resume_id": RESUME},
                {"user_id": USER, "job_family": "software_engineer", "resume_id": SECOND},
                # Deliberately malformed legacy data must not bypass ownership.
                {"user_id": USER, "job_family": "data_analyst", "resume_id": FOREIGN},
                {"user_id": OTHER, "job_family": "ai_engineer", "resume_id": FOREIGN},
            ])
        self.sessions = []
        def factory():
            session = Session(self.engine)
            session.commit = Mock(wraps=session.commit)
            session.rollback = Mock(wraps=session.rollback)
            session.close = Mock(wraps=session.close)
            self.sessions.append(session)
            return session
        self.source = ReadOnlyResumeSource(factory)

    def assert_released_without_commit(self):
        self.assertTrue(self.sessions)
        for session in self.sessions:
            session.commit.assert_not_called()
            session.rollback.assert_called()
            session.close.assert_called()

    def test_exact_owned_direction_returns_detached_skills_without_rewriting_data(self):
        before = deepcopy(self.saved)
        result = self.source.get_snapshot(USER, "ai_engineer")
        self.assertIsInstance(result, ResumeSnapshot)
        self.assertEqual(result.id, RESUME)
        self.assertEqual(result.job_family, "ai_engineer")
        self.assertEqual(result.filename, "confirmed.pdf")
        self.assertEqual(result.confirmed_data["technical_skills"], before["technical_skills"])
        self.assertEqual(result.confirmed_data, before)
        self.assertEqual(self.source.get_snapshot(USER, "software_engineer").id, SECOND)
        self.assertEqual(self.source.get_snapshot(OTHER, "ai_engineer").id, FOREIGN)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(self.resumes.c.confirmed_data).where(self.resumes.c.id == RESUME)), before)
        self.assert_released_without_commit()

    def test_foreign_missing_and_unbound_direction_never_fall_back_to_another_resume(self):
        cases = [(MISSING, "ai_engineer", 403), (USER, "data_analyst", 404), (OTHER, "software_engineer", 404)]
        for user, family, status in cases:
            with self.subTest(user=user, family=family), self.assertRaises(HTTPException) as caught:
                self.source.get_snapshot(user, family)
            self.assertEqual(caught.exception.status_code, status)
            self.assertNotIn("Private foreign skill", str(caught.exception.detail))
        with self.engine.begin() as connection:
            connection.execute(update(self.destinations).where(self.destinations.c.user_id == USER,
                self.destinations.c.job_family == "ai_engineer").values(resume_id=MISSING))
        with self.assertRaises(HTTPException) as caught:
            self.source.get_snapshot(USER, "ai_engineer")
        self.assertEqual(caught.exception.status_code, 404)
        self.assert_released_without_commit()

    def test_invalid_saved_payload_is_sanitized_and_transaction_released(self):
        with self.engine.begin() as connection:
            connection.execute(update(self.resumes).where(self.resumes.c.id == RESUME)
                .values(confirmed_data={"private-invalid": "private-content"}))
        with self.assertRaises(HTTPException) as caught:
            self.source.get_snapshot(USER, "ai_engineer")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertNotIn("private-", str(caught.exception.detail))
        self.assert_released_without_commit()

    def test_sql_and_connection_failures_are_sanitized_without_retry(self):
        with patch.object(Session, "connection", side_effect=SQLAlchemyError("private-connection-details")):
            with self.assertRaises(HTTPException) as caught:
                self.source.get_snapshot(USER, "ai_engineer")
            self.assertEqual(caught.exception.status_code, 503)
            self.assertNotIn("private-", str(caught.exception.detail))
        failed_queries = []
        def fail_query(connection, cursor, statement, parameters, context, executemany):
            failed_queries.append(statement)
            raise SQLAlchemyError("private-db-password-and-user-content")
        event.listen(self.engine, "before_cursor_execute", fail_query)
        try:
            with self.assertRaises(HTTPException) as caught:
                self.source.get_snapshot(USER, "ai_engineer")
            self.assertEqual(caught.exception.status_code, 503)
            self.assertNotIn("private-", str(caught.exception.detail))
            self.assertEqual(len(failed_queries), 1)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_query)
        self.assert_released_without_commit()

    def test_writes_ddl_and_raw_sql_are_rejected_before_reaching_sqlite(self):
        attempted = [insert(self.users).values(id=MISSING),
            update(self.users).where(self.users.c.id == USER).values(id=MISSING),
            delete(self.users).where(self.users.c.id == USER),
            CreateTable(Table("blocked_creation", MetaData(), Column("id", Integer))),
            text("SELECT 1"), text("DELETE FROM users"),
            select(self.users.c.id).with_for_update(),
            select(self.users.c.id).add_cte(delete(self.users).where(self.users.c.id == USER).cte("blocked_delete"))]
        for statement in attempted:
            with self.subTest(statement=type(statement).__name__), self.assertRaises(CopilotReadOnlyError):
                with self.source._session() as session:
                    session.execute(statement)
        with self.engine.connect() as connection:
            self.assertEqual(set(connection.scalars(select(self.users.c.id))), {USER, OTHER})
            # Guards belong to the reader's private Connection, not the pooled DBAPI connection.
            connection.execute(text("SELECT 1"))
        self.assert_released_without_commit()

    def test_explicit_orm_flush_is_blocked_without_inserting_a_user(self):
        with self.assertRaises(CopilotReadOnlyError):
            with self.source._session() as session:
                session.add(User(id=MISSING))
                session.flush()
        with self.engine.connect() as connection:
            self.assertEqual(set(connection.scalars(select(self.users.c.id))), {USER, OTHER})
        self.assert_released_without_commit()

    def test_session_commit_is_blocked_and_rollback_does_not_leak_listeners(self):
        with self.assertRaises(CopilotReadOnlyError):
            with self.source._session() as session:
                session.commit()
        # A subsequent isolated read succeeds after the rejected commit.
        self.assertEqual(self.source.get_snapshot(USER, "ai_engineer").id, RESUME)
        self.sessions[0].rollback.assert_called()
        self.sessions[0].close.assert_called()
        self.sessions[-1].commit.assert_not_called()


class ReadOnlyTransactionSetupTests(NoNetwork):
    def session(self, *, setting_error=None):
        timeline = []
        session = MagicMock(spec=Session)
        session.__enter__.return_value = session
        def close_session(*_):
            session.close()
            return False
        session.__exit__.side_effect = close_session
        session.no_autoflush = nullcontext()
        connection = MagicMock()
        connection.dialect.name = "postgresql"
        session.connection.return_value = connection
        def configure(statement):
            timeline.append(statement)
            if setting_error:
                raise setting_error
        connection.exec_driver_sql.side_effect = configure
        session.rollback.side_effect = lambda: timeline.append("rollback")
        source = ReadOnlyResumeSource(lambda: session)
        return source, session, connection, timeline

    def test_postgresql_read_only_is_set_before_any_consumer_query_and_then_rolled_back(self):
        source, session, connection, timeline = self.session()
        with patch.object(readonly.event, "listen"), patch.object(readonly.event, "remove"):
            with source._session():
                timeline.append("consumer query")
        self.assertEqual(timeline, ["SET TRANSACTION READ ONLY", "consumer query", "rollback"])
        connection.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
        session.commit.assert_not_called()
        session.close.assert_called()

    def test_failed_postgresql_read_only_setting_stops_before_business_select_and_closes(self):
        source, session, connection, timeline = self.session(setting_error=SQLAlchemyError("private-setting-details"))
        with patch.object(readonly.event, "listen"), patch.object(readonly.event, "remove"):
            with self.assertRaises(HTTPException) as caught:
                source.get_snapshot(USER, "ai_engineer")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("private-", str(caught.exception.detail))
        session.execute.assert_not_called()
        session.scalar.assert_not_called()
        session.commit.assert_not_called()
        session.close.assert_called()


if __name__ == "__main__":
    unittest.main()
