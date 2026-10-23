"""Shared, current job analyses: one parent and five ordered collections.

These models prepare future PostgreSQL persistence only. The active JD pipeline
still uses local storage. No user/resume ownership or candidate evaluation belongs
here. Validate the current output contract and source evidence before saving all
six tables in one transaction; a forced replacement rebuilds all child rows.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JOB_FAMILIES = ("software_engineer", "data_analyst", "ai_engineer")
SENIORITIES = (
    "intern", "new_grad", "entry_level", "mid_level", "senior", "staff",
    "senior_staff", "principal", "manager", "multiple_levels",
)
QUALIFICATION_LEVELS = ("required", "preferred", "unspecified")
QUALIFICATION_CATEGORIES = (
    "skill", "experience", "education", "certification", "domain_knowledge",
    "language", "competency", "other",
)
CONDITION_TYPES = (
    "employment_type", "workplace_arrangement", "geographic_restriction", "schedule",
    "travel", "visa_sponsorship", "work_authorization", "citizenship_requirement",
    "security_clearance", "export_control", "other",
)
COMPENSATION_TYPES = (
    "base_salary", "hourly_rate", "ote", "bonus", "commission", "equity", "stipend", "other",
)
PAY_INTERVALS = ("hour", "day", "week", "month", "year", "one_time")


def _sql_values(values: tuple[str, ...]) -> str:
    # Internal, fixed contract enums only; never accepts source/job/user text.
    return ", ".join(f"'{value}'" for value in values)


def _enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN ({_sql_values(values)})", name=name)


class JobPostingAnalysis(Base):
    """One successfully validated analysis per existing source posting.

    This 10-column projection stores derived requirements, not a duplicate of the
    full 28-field Agent response. Join job_postings for source metadata and use
    its closed_at to determine availability. source_content_hash records the
    version actually analyzed, even when the current source has since changed.

    Company, title and department use source values: v13 preserves explicit names
    rather than canonicalizing them, but can supplement missing metadata from the
    description. Such Agent-only enrichment remains in the local JSON, not here.
    Salary currency/interval summaries are omitted: compensation rows retain the
    individual arrangements. Neither a JOIN nor this projection promises an exact
    reconstruction of the original Agent response.
    """

    __tablename__ = "job_postings_analyses"
    __table_args__ = (
        _enum_check("job_family", JOB_FAMILIES, "ck_jpa_job_family"),
        _enum_check("seniority", SENIORITIES, "ck_jpa_seniority"),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(role_overview_evidence) = 'array' THEN "
            "CASE WHEN role_overview IS NULL THEN jsonb_array_length(role_overview_evidence) = 0 "
            "ELSE btrim(role_overview) <> '' AND jsonb_array_length(role_overview_evidence) > 0 END "
            "ELSE false END",
            name="ck_jpa_overview_evidence",
        ),
        CheckConstraint(
            "(cardinality(other_relevant_information) = 0 OR array_ndims(other_relevant_information) = 1) "
            "AND array_position(other_relevant_information, NULL) IS NULL",
            name="ck_jpa_other_information_array",
        ),
        Index("ix_jpa_family_seniority", "job_family", "seniority"),
    )

    # Same UUID as the original job; never generate a second identity here.
    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), primary_key=True
    )
    job_family: Mapped[str | None] = mapped_column(Text)
    seniority: Mapped[str | None] = mapped_column(Text)
    role_overview: Mapped[str | None] = mapped_column(Text)
    role_overview_evidence: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB(none_as_null=True), default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    benefits: Mapped[str | None] = mapped_column(Text)
    other_relevant_information: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'"), nullable=False
    )
    source_content_hash: Mapped[str | None] = mapped_column(Text)
    # Supplied by the backend from the successful analysis, not by the Agent or
    # INSERT defaults. Importing a local result must preserve its analysis time.
    agent_version: Mapped[str] = mapped_column(Text, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class _AnalysisChild:
    """One logically complete output item. Evidence stays with its item as JSONB."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), sort_order=-3
    )
    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_postings_analyses.job_posting_id", ondelete="CASCADE"),
        nullable=False, sort_order=-2,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, sort_order=-1)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, str]]] = mapped_column(JSONB(none_as_null=True), nullable=False)


def _child_constraints(short_name: str) -> tuple:
    return (
        # The leading job_posting_id also supports per-job reads; no redundant index.
        UniqueConstraint("job_posting_id", "position", name=f"uq_{short_name}_position"),
        CheckConstraint("position >= 0", name=f"ck_{short_name}_position"),
        CheckConstraint("btrim(value) <> ''", name=f"ck_{short_name}_value"),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(evidence) = 'array' "
            "THEN jsonb_array_length(evidence) > 0 ELSE false END",
            name=f"ck_{short_name}_evidence",
        ),
    )


class JobAnalysisLocation(_AnalysisChild, Base):
    """A work-location entity, not inferred country/city or residence eligibility."""

    __tablename__ = "job_analysis_locations"
    __table_args__ = _child_constraints("jal")


class JobAnalysisResponsibility(_AnalysisChild, Base):
    __tablename__ = "job_analysis_responsibilities"
    __table_args__ = _child_constraints("jar")


class JobAnalysisQualification(_AnalysisChild, Base):
    """A JOB requirement, including its alternatives; never a user's skill gap."""

    __tablename__ = "job_analysis_qualifications"
    __table_args__ = (
        *_child_constraints("jaq"),
        _enum_check("level", QUALIFICATION_LEVELS, "ck_jaq_level"),
        CheckConstraint(
            "array_ndims(categories) = 1 AND cardinality(categories) > 0 "
            "AND array_position(categories, NULL) IS NULL "
            f"AND categories <@ ARRAY[{_sql_values(QUALIFICATION_CATEGORIES)}]::text[]",
            name="ck_jaq_categories",
        ),
    )

    level: Mapped[str] = mapped_column(Text, nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)


class JobAnalysisCondition(_AnalysisChild, Base):
    __tablename__ = "job_analysis_conditions"
    __table_args__ = (
        *_child_constraints("jac"),
        _enum_check("type", CONDITION_TYPES, "ck_jac_type"),
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)


class JobAnalysisCompensation(_AnalysisChild, Base):
    __tablename__ = "job_analysis_compensation"
    __table_args__ = (
        *_child_constraints("jap"),
        _enum_check("type", COMPENSATION_TYPES, "ck_jap_type"),
        _enum_check("interval", PAY_INTERVALS, "ck_jap_interval"),
        CheckConstraint(
            "minimum >= 0 AND minimum NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_jap_minimum",
        ),
        CheckConstraint(
            "maximum >= 0 AND maximum NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_jap_maximum",
        ),
        CheckConstraint("minimum <= maximum", name="ck_jap_bounds"),
        CheckConstraint("btrim(currency) <> ''", name="ck_jap_currency"),
        CheckConstraint("btrim(applies_to) <> ''", name="ck_jap_applies_to"),
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)
    minimum: Mapped[Decimal | None] = mapped_column(Numeric)
    maximum: Mapped[Decimal | None] = mapped_column(Numeric)
    currency: Mapped[str | None] = mapped_column(Text)
    interval: Mapped[str | None] = mapped_column(Text)
    applies_to: Mapped[str | None] = mapped_column(Text)
