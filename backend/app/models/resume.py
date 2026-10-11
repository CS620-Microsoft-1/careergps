import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class ResumeStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class ResumeError(StrEnum):
    NO_TEXT = "no_text"  # under the text threshold, most likely a scanned PDF
    LLM_INVALID_OUTPUT = "llm_invalid_output"
    LLM_UNAVAILABLE = "llm_unavailable"
    INTERNAL = "internal"


class Resume(Base):
    """One uploaded PDF and its parsing state. P0: at most one per user (unique user_id)."""

    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # resumes/<user_id>/<resume_id>.pdf; never built from the uploaded file name.
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ResumeStatus.PENDING)
    error_code: Mapped[str | None] = mapped_column(String(50))
    # Personal data: never log these two.
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    parsed_data: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    parser_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Resume {self.id} {self.status}>"
