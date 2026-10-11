"""Structured résumé data. Written only when the user confirms a parsed résumé."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType

# Dates are "YYYY" or "YYYY-MM" strings: résumés rarely give exact days.
DATE_LENGTH = 7


class _ResumeRow:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Education(_ResumeRow, Base):
    __tablename__ = "educations"

    school: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[str | None] = mapped_column(String(DATE_LENGTH))
    end_date: Mapped[str | None] = mapped_column(String(DATE_LENGTH))
    gpa: Mapped[str | None] = mapped_column(String(20))


class Experience(_ResumeRow, Base):
    __tablename__ = "experiences"

    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[str | None] = mapped_column(String(DATE_LENGTH))
    end_date: Mapped[str | None] = mapped_column(String(DATE_LENGTH))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text)  # bullet points, one per line


class Skill(_ResumeRow, Base):
    __tablename__ = "skills"
    __table_args__ = (
        Index("skills_user_id_lower_name_key", "user_id", text("lower(name)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)


class Project(_ResumeRow, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    technologies: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
