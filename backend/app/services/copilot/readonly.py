"""Isolated, read-only database access for Copilot's staged data integration.

Only fixed server-owned queries are exposed; identity is provided by the backend.
"""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import get_args
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import visitors

from app.models import Destination, Resume, User
from app.schemas.resume import ResumeClassification
from app.schemas.skill_gap_web import JobFamily

def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResumeSnapshot:
    id: UUID
    user_id: UUID
    job_family: JobFamily
    filename: str
    confirmed_at: datetime
    confirmed_data: dict
    resume_hash: str


class CopilotReadOnlyError(RuntimeError):
    """An operation fell outside the private Copilot read boundary."""


def select_only(connection, cursor, statement, parameters, context, executemany):
    """Reject raw SQL, writes, locking reads and data-modifying CTEs.

    The PostgreSQL read-only transaction is an additional database-level guard.
    Neither SQL nor SQLAlchemy expressions can be supplied through the public API.
    """
    compiled = getattr(getattr(context, "compiled", None), "statement", None)
    if not getattr(compiled, "is_select", False):
        raise CopilotReadOnlyError("Copilot database access only permits fixed SELECT queries.")
    for node in visitors.iterate(compiled):
        if getattr(node, "is_dml", False) or getattr(node, "_for_update_arg", None) is not None:
            raise CopilotReadOnlyError("Copilot database access only permits non-locking SELECT queries.")


def _reject_commit(session):
    raise CopilotReadOnlyError("Copilot read sessions cannot commit.")


def _reject_flush(session, flush_context, instances):
    raise CopilotReadOnlyError("Copilot read sessions cannot flush changes.")


class ReadOnlyResumeSource:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        # A fresh session never carries pending changes from an account-edit request.
        with self.session_factory() as session, session.no_autoflush:
            connection = None
            guarded = False
            event.listen(session, "before_commit", _reject_commit)
            event.listen(session, "before_flush", _reject_flush)
            try:
                connection = session.connection()
                if connection.dialect.name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                elif connection.dialect.name != "sqlite":
                    # SQLite is only supported for isolated offline test fixtures.
                    raise CopilotReadOnlyError("This database does not support Copilot read sessions.")
                event.listen(connection, "before_cursor_execute", select_only)
                guarded = True
                yield session
            finally:
                try:
                    # Never commit, including on success. Release the transaction before returning.
                    session.rollback()
                finally:
                    if guarded:
                        event.remove(connection, "before_cursor_execute", select_only)
                    event.remove(session, "before_commit", _reject_commit)
                    event.remove(session, "before_flush", _reject_flush)

    @staticmethod
    def _owner(user_id: UUID) -> UUID:
        try:
            return UUID(str(user_id))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(401, "Not authenticated") from None

    def require_account(self, user_id: UUID) -> None:
        owner = self._owner(user_id)
        try:
            with self._session() as session:
                if session.scalar(select(User.id).where(User.id == owner)) is None:
                    raise HTTPException(403, "Finish onboarding first")
        except (SQLAlchemyError, CopilotReadOnlyError):
            raise HTTPException(503, "The account could not be read. Please try again.") from None

    def get_snapshot(self, user_id: UUID, job_family: JobFamily) -> ResumeSnapshot:
        if job_family not in get_args(JobFamily):
            raise HTTPException(422, "Choose a supported career direction.")
        owner = self._owner(user_id)
        try:
            with self._session() as session:
                if session.scalar(select(User.id).where(User.id == owner)) is None:
                    raise HTTPException(403, "Finish onboarding first")
                query = (select(Resume.id, Resume.original_filename, Resume.confirmed_data, Resume.created_at)
                         .select_from(Destination)
                         .join(Resume, and_(Resume.id == Destination.resume_id,
                                            Resume.user_id == Destination.user_id))
                         .where(Destination.user_id == owner,
                                Destination.job_family == job_family,
                                Resume.user_id == owner))
                row = session.execute(query).mappings().one_or_none()
                if row is None:
                    raise HTTPException(404, "No confirmed resume is saved for this career direction.")
                try:
                    confirmed = ResumeClassification.model_validate(deepcopy(row["confirmed_data"])).model_dump(mode="json")
                    return ResumeSnapshot(
                        id=row["id"], user_id=owner, filename=row["original_filename"],
                        job_family=job_family, confirmed_data=confirmed,
                        confirmed_at=row["created_at"], resume_hash=canonical_hash(confirmed))
                except (ValidationError, TypeError, ValueError):
                    raise HTTPException(409, "The saved resume needs to be reviewed and saved again.") from None
        except (SQLAlchemyError, CopilotReadOnlyError):
            raise HTTPException(503, "The confirmed resume could not be read. Please try again.") from None
