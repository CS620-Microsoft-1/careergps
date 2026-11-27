import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Numeric, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

AGENT_CALL_STATUSES = ("completed", "incomplete", "failed", "cancelled", "queued", "in_progress", "error", "timeout")


class AgentCall(Base):
    """One Foundry Agent request: who asked, how long it took, its tokens and estimated cost.

    Never holds prompts or answers (they carry résumé content). Written by app.services.agent_calls.
    """

    __tablename__ = "agent_calls"
    __table_args__ = (
        CheckConstraint(f"status IN {AGENT_CALL_STATUSES}", name="ck_agent_calls_status"),
        CheckConstraint("latency_ms >= 0", name="ck_agent_calls_latency_ms"),
        CheckConstraint("input_tokens >= 0 AND cached_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0",
                        name="ck_agent_calls_tokens"),
        CheckConstraint("cost_usd >= 0", name="ck_agent_calls_cost_usd"),
        Index("ix_agent_calls_created_at", "created_at"),
        Index("ix_agent_calls_agent_created_at", "agent", "created_at"),
        Index("ix_agent_calls_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # The Foundry Agent name and, when pinned, its version.
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    agent_version: Mapped[str | None] = mapped_column(Text)
    # The model the response reports; None when the call failed before a response.
    model: Mapped[str | None] = mapped_column(Text)
    # The signed-in student (a Supabase Auth id; onboarding calls come before the users row exists).
    # The foreign key to auth.users (ON DELETE SET NULL) lives only in the migration, as for users.id.
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    # The Skill Gap run the call belongs to, if any.
    run_id: Mapped[uuid.UUID | None] = mapped_column()
    # The response's own status, or error/timeout when the request raised.
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Exception class name only; messages can carry résumé data.
    error_type: Mapped[str | None] = mapped_column(Text)
    # Wall time of responses.create alone (not conversation create/delete).
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    # Estimate from app.services.model_prices; None when the model has no listed price or usage is missing.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8))

    def __repr__(self) -> str:
        return f"<AgentCall {self.agent} {self.status} {self.latency_ms}ms>"
