import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

AUDIT_SOURCES = ("api", "script")


class AuditLog(Base):
    """One data write: what changed, whose data it was, and whether the student or a script did it.

    Written by app.services.audit, in the same transaction as the write it describes. Agent calls are
    in agent_calls; the audit_events view shows both as one timeline.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(f"source IN {AUDIT_SOURCES}", name="ck_audit_log_source"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_audit_log_details_object"),
        Index("ix_audit_log_created_at", "created_at"),
        Index("ix_audit_log_user_id_created_at", "user_id", "created_at"),
        Index("ix_audit_log_action", "action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # The student whose data changed (a Supabase Auth id); None for shared data such as the catalog.
    # The foreign key to auth.users (ON DELETE CASCADE) lives only in the migration, as for users.id.
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    # What happened, as <area>.<event>, e.g. resume.added, plan.item_saved.
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    # Ids, statuses, counts and changed field names only; never résumé content or field values.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    # api: a signed-in request (or work it started); script: a command run by an operator.
    source: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.target_type}:{self.target_id}>"
