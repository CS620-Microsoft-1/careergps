"""The audit log: one audit_log row per data write.

Database writes add their row to the same session before committing, so the write and its record
commit or roll back together:

    audit.record(session, "course.marked_taken", user_id=user_id, target=("school_course", course_id))
    session.commit()

Writes outside the database (the plan's local JSON files) use record_detached(), which writes in its
own session after the file is saved; a failure there is logged, not raised.

`details` holds ids, statuses, counts and changed field names, never résumé content or field values.
Every write method must record (tests/test_audit.py lists them). Agent calls are in agent_calls; the
audit_events view joins both.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.services import agent_calls

logger = logging.getLogger(__name__)

Target = tuple[str, Any]


def record(session: Session, action: str, *, user_id: uuid.UUID | str | None = None,
           target: Target | None = None, details: dict[str, Any] | None = None) -> None:
    """Add one audit_log row to `session`; the caller's commit writes it with the change."""
    from app.models.audit_log import AuditLog

    session.add(AuditLog(**_row(action, user_id, target, details)))


class DetachedWriter(Protocol):
    def write(self, row: dict[str, Any]) -> None: ...


class DatabaseWriter:
    """Each row in its own short transaction."""

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def write(self, row: dict[str, Any]) -> None:
        if self._session_factory is None:
            from app.db.session import SessionLocal  # Lazy: importing it needs DATABASE_URL.

            self._session_factory = SessionLocal
        from app.models.audit_log import AuditLog

        with self._session_factory() as session:
            session.add(AuditLog(**row))
            session.commit()


class MemoryWriter:
    """Keeps rows in a list; for tests."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def write(self, row: dict[str, Any]) -> None:
        self.rows.append(row)


_writer: DetachedWriter | None = None


def use_writer(writer: DetachedWriter) -> None:
    global _writer
    _writer = writer


def record_detached(action: str, *, user_id: uuid.UUID | str | None = None, target: Target | None = None,
                    details: dict[str, Any] | None = None) -> None:
    """For writes outside the database: record in a separate transaction. Never raises."""
    global _writer
    try:
        if _writer is None:
            _writer = DatabaseWriter()
        _writer.write(_row(action, user_id, target, details))
    except Exception as error:
        logger.warning("Could not write audit record %s (%s)", action, type(error).__name__)


def _row(action: str, user_id: uuid.UUID | str | None, target: Target | None,
         details: dict[str, Any] | None) -> dict[str, Any]:
    owner = user_id if user_id is not None else agent_calls.current_user_id()
    target_type, target_id = target if target is not None else (None, None)
    return {
        "user_id": uuid.UUID(str(owner)) if owner is not None else None,
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id is not None else None,
        "details": details or {},
        "source": "api" if agent_calls.in_request() else "script",
    }
