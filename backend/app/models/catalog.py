"""The curated catalog: certifications, school courses and student organizations.

Rows are never deleted and ids never change: plan items and other tables refer to them by id.
A resource that is no longer offered gets active = false. Skills are skill_ids from
app/services/skill_gaps/data/core_catalog.json, checked in Python (app/services/catalog_writes.py),
because the skill catalog is a file, not a table. Online courses and projects are still files.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Index, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class _CatalogRow:
    """Columns every catalog table shares."""

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Position in the list the API returns; new rows go last.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # The page last used to check this row.
    source_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CatalogCertification(_CatalogRow, Base):
    """One certification; skills are listed per job family."""

    __tablename__ = "certifications"
    __table_args__ = (
        CheckConstraint("btrim(id) <> ''", name="ck_certifications_id"),
        CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')", name="ck_certifications_level"),
        CheckConstraint("cost_usd >= 0", name="ck_certifications_cost_usd"),
        CheckConstraint("jsonb_typeof(skills) = 'object'", name="ck_certifications_skills"),
        Index("ix_certifications_active_sort_order", "active", "sort_order"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # None when the price depends on a subscription or is not published.
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    cost_note: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    # {"software_engineer": ["cloud"], ...}
    skills: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_verified: Mapped[date] = mapped_column(Date, nullable=False)


class _SchoolResource(_CatalogRow):
    """Columns school courses and student organizations share; skills are not split by role."""

    school: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[list] = mapped_column(JSONB, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    # None until someone checks the row against the school's own pages.
    last_verified: Mapped[date | None] = mapped_column(Date)


class SchoolCourse(_SchoolResource, Base):
    __tablename__ = "school_courses"
    __table_args__ = (
        CheckConstraint("btrim(id) <> ''", name="ck_school_courses_id"),
        CheckConstraint("jsonb_typeof(skills) = 'array'", name="ck_school_courses_skills"),
        Index("ix_school_courses_school_active", "school", "active"),
    )


class StudentOrg(_SchoolResource, Base):
    __tablename__ = "student_orgs"
    __table_args__ = (
        CheckConstraint("btrim(id) <> ''", name="ck_student_orgs_id"),
        CheckConstraint("jsonb_typeof(skills) = 'array'", name="ck_student_orgs_skills"),
        Index("ix_student_orgs_school_active", "school", "active"),
    )

    # True for ongoing commitments that run next to the main plan.
    alongside: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)


class CatalogVersion(Base):
    """A version string per catalog. Cached certification recommendations are kept only while
    the "certifications" version is unchanged."""

    __tablename__ = "catalog_versions"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
