"""Confirmed résumés. A row is written only when the student presses "Looks right"; unverified Agent
output is never stored.

`resumes.confirmed_data` keeps all 13 sections exactly as confirmed and is the source of truth. The child
tables hold the parts the agents query, and are deleted and rebuilt from `confirmed_data` on every edit.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Python fills ids so child rows can reference a résumé before it is flushed; the database default
# covers rows inserted any other way.
_UUID_DEFAULT = {"default": uuid.uuid4, "server_default": text("gen_random_uuid()")}


def _empty_array() -> Any:
    return text("'{}'")


class Resume(Base):
    """One confirmed résumé version. A user keeps every version; destinations pick which one each role uses."""

    __tablename__ = "resumes"
    __table_args__ = (
        # Lets child rows and destinations check that the résumé belongs to the same user.
        UniqueConstraint("id", "user_id", name="uq_resumes_id_user_id"),
        CheckConstraint("file_type IN ('pdf', 'docx')", name="ck_resumes_file_type"),
        CheckConstraint("jsonb_typeof(confirmed_data) = 'object'", name="ck_resumes_confirmed_data_object"),
        Index("ix_resumes_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, **_UUID_DEFAULT)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Optional name the student gives this version, e.g. "Data Analyst version".
    label: Mapped[str | None] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # How the text was read, from POST /resumes/analyze.
    parser: Mapped[str] = mapped_column(String(50), nullable=False)
    ocr_pages: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), server_default=_empty_array(), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Version of the ResumeClassification contract that confirmed_data follows.
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # Personal data: never log it.
    confirmed_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # A row exists only once confirmed, so created_at is the confirmation time.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Resume {self.id} {self.original_filename!r}>"


class _ResumeChild:
    """Columns shared by every table derived from confirmed_data. Rows are rebuilt, never updated."""

    # sort_order puts these columns first (and created_at last) in each table.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, sort_order=-3, **_UUID_DEFAULT)
    resume_id: Mapped[uuid.UUID] = mapped_column(nullable=False, sort_order=-2)
    # Repeats the résumé's owner so "all of a user's skills" is a one-table query.
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True, sort_order=-1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, sort_order=1
    )


def _belongs_to_resume(table: str) -> ForeignKeyConstraint:
    """(resume_id, user_id) must match a résumé and its owner; deleting the résumé deletes the row."""
    return ForeignKeyConstraint(
        ["resume_id", "user_id"],
        ["resumes.id", "resumes.user_id"],
        name=f"fk_{table}_resume",
        ondelete="CASCADE",
    )


def _date_precision_check(table: str) -> CheckConstraint:
    return CheckConstraint(
        "date_precision IN ('month', 'year')", name=f"ck_{table}_date_precision"
    )


class ResumeExperience(_ResumeChild, Base):
    """Work experience, research experience and leadership activities."""

    __tablename__ = "resume_experiences"
    __table_args__ = (
        _belongs_to_resume(__tablename__),
        UniqueConstraint("resume_id", "kind", "position", name="uq_resume_experiences_position"),
        CheckConstraint("kind IN ('work', 'research', 'leadership')", name="ck_resume_experiences_kind"),
        CheckConstraint("position >= 0", name="ck_resume_experiences_position"),
        CheckConstraint(
            "organization IS NOT NULL OR title IS NOT NULL OR cardinality(content) > 0",
            name="ck_resume_experiences_not_blank",
        ),
        _date_precision_check(__tablename__),
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Order within its section on the résumé.
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # company (work) or organization (research, leadership)
    organization: Mapped[str | None] = mapped_column(String(255))
    # title (work, research) or role (leadership)
    title: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    # One string per bullet point.
    content: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_empty_array(), nullable=False)
    # As confirmed: "2024-05", "2024" or "Present".
    start_date: Mapped[str | None] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20))
    # Derived for calculations; NULL when the text doesn't parse. Year-only dates use January for the
    # start and December for the end.
    start_month: Mapped[date | None] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str | None] = mapped_column(String(10))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)

    def __repr__(self) -> str:
        return f"<ResumeExperience {self.kind} {self.organization!r}>"


class ResumeEducation(_ResumeChild, Base):
    __tablename__ = "resume_educations"
    __table_args__ = (
        _belongs_to_resume(__tablename__),
        UniqueConstraint("resume_id", "position", name="uq_resume_educations_position"),
        CheckConstraint("position >= 0", name="ck_resume_educations_position"),
        CheckConstraint(
            "degree_level IN ('associate', 'bachelor', 'master', 'doctorate', 'other')",
            name="ck_resume_educations_degree_level",
        ),
        CheckConstraint("gpa_value >= 0", name="ck_resume_educations_gpa_value"),
        CheckConstraint("gpa_scale > 0", name="ck_resume_educations_gpa_scale"),
        CheckConstraint(
            "institution IS NOT NULL OR degree IS NOT NULL OR major IS NOT NULL",
            name="ck_resume_educations_not_blank",
        ),
        _date_precision_check(__tablename__),
    )

    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    institution: Mapped[str | None] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(255))
    major: Mapped[str | None] = mapped_column(String(255))
    # As confirmed, e.g. "3.8/4.0".
    gpa: Mapped[str | None] = mapped_column(String(20))
    # Coursework and other details, one string per line.
    content: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_empty_array(), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(20))
    # Graduation date, actual or expected.
    end_date: Mapped[str | None] = mapped_column(String(20))
    # Derived; NULL when the text doesn't parse. Year-only dates use January for the start and May for
    # the end (the usual graduation month).
    degree_level: Mapped[str | None] = mapped_column(String(20))
    gpa_value: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gpa_scale: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    start_month: Mapped[date | None] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str | None] = mapped_column(String(10))

    def __repr__(self) -> str:
        return f"<ResumeEducation {self.institution!r}>"


class ResumeProject(_ResumeChild, Base):
    __tablename__ = "resume_projects"
    __table_args__ = (
        _belongs_to_resume(__tablename__),
        UniqueConstraint("resume_id", "position", name="uq_resume_projects_position"),
        CheckConstraint("position >= 0", name="ck_resume_projects_position"),
        CheckConstraint(
            "name IS NOT NULL OR cardinality(content) > 0", name="ck_resume_projects_not_blank"
        ),
    )

    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2048))
    # As written; also copied into resume_skills with source 'project'.
    technologies: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=_empty_array(), nullable=False
    )
    content: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_empty_array(), nullable=False)

    def __repr__(self) -> str:
        return f"<ResumeProject {self.name!r}>"


class ResumeAchievement(_ResumeChild, Base):
    """Certifications and awards/honors."""

    __tablename__ = "resume_achievements"
    __table_args__ = (
        _belongs_to_resume(__tablename__),
        UniqueConstraint("resume_id", "kind", "position", name="uq_resume_achievements_position"),
        CheckConstraint("kind IN ('certification', 'award')", name="ck_resume_achievements_kind"),
        CheckConstraint("position >= 0", name="ck_resume_achievements_position"),
        # Awards have no URL field in the résumé contract.
        CheckConstraint("kind = 'certification' OR url IS NULL", name="ck_resume_achievements_url"),
        _date_precision_check(__tablename__),
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2048))
    content: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_empty_array(), nullable=False)
    # Free text as confirmed, e.g. "May 2024" or "Spring 2023".
    issued_date: Mapped[str | None] = mapped_column(String(50))
    # Derived; NULL when the text doesn't parse. Year-only dates use January.
    issued_month: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str | None] = mapped_column(String(10))

    def __repr__(self) -> str:
        return f"<ResumeAchievement {self.kind} {self.name!r}>"


class ResumeSkill(_ResumeChild, Base):
    """One piece of evidence for a skill. The same skill can appear once per place it was found."""

    __tablename__ = "resume_skills"
    __table_args__ = (
        _belongs_to_resume(__tablename__),
        # Also serves lookups by (resume_id, normalized_name).
        UniqueConstraint(
            "resume_id",
            "normalized_name",
            "source",
            "source_project_id",
            "source_achievement_id",
            "source_experience_id",
            "source_education_id",
            name="uq_resume_skills_evidence",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "source IN ('listed', 'project', 'certification', 'experience', 'education')",
            name="ck_resume_skills_source",
        ),
        # Exactly the link that matches the source is set; 'listed' has none.
        CheckConstraint(
            "num_nonnulls(source_project_id, source_achievement_id, source_experience_id,"
            " source_education_id) = CASE WHEN source = 'listed' THEN 0 ELSE 1 END"
            " AND (source <> 'project' OR source_project_id IS NOT NULL)"
            " AND (source <> 'certification' OR source_achievement_id IS NOT NULL)"
            " AND (source <> 'experience' OR source_experience_id IS NOT NULL)"
            " AND (source <> 'education' OR source_education_id IS NOT NULL)",
            name="ck_resume_skills_source_link",
        ),
        CheckConstraint(
            "position IS NULL OR (source = 'listed' AND position >= 0)",
            name="ck_resume_skills_position",
        ),
    )

    # As written, e.g. "PostgreSQL".
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Join key with market skills; both sides must use the same normalization and aliases.
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_projects.id", ondelete="CASCADE")
    )
    source_achievement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_achievements.id", ondelete="CASCADE")
    )
    source_experience_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_experiences.id", ondelete="CASCADE")
    )
    source_education_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_educations.id", ondelete="CASCADE")
    )
    # The bullet or coursework line the skill was found in (experience and education sources).
    evidence_text: Mapped[str | None] = mapped_column(Text)
    # Order in the Technical Skills list ('listed' only).
    position: Mapped[int | None] = mapped_column(SmallInteger)

    def __repr__(self) -> str:
        return f"<ResumeSkill {self.normalized_name} from {self.source}>"
