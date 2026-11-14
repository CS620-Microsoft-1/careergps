"""Skill Gap analyses: one run per (résumé, role, configuration), its three Agent groups and one row per skill.

Mirrors migrations 6d7e2b9a4c15 (skill_gap_runs) and df5726089a8e (new run columns, branches and results);
docs/contracts/skill-gap-run-storage.schema.json v3 describes the stored record. `skill_gap_runs.report` is
the full v12 report the API returns. `skill_gap_results` is its queryable copy, written once with it.
Agent answers and quotes come from the student's résumé: personal data, never log them.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_UUID_DEFAULT = {"default": uuid.uuid4, "server_default": text("gen_random_uuid()")}
_SHA256 = "~ '^[0-9a-f]{64}$'"
# Python None is SQL NULL, never a JSON null, so "IS NULL" checks and jsonb_typeof checks hold.
_NULLABLE_JSONB = JSONB(none_as_null=True)
_JOB_FAMILIES = "('software_engineer', 'data_analyst', 'ai_engineer')"
_GROUPS = "('foundation', 'lifecycle', 'systems')"

STORAGE_SCHEMA_VERSION = "careergps.skill_gap_run_storage.v3"
_STORAGE_VERSIONS = ("('careergps.skill_gap_run_storage.v1', 'careergps.skill_gap_run_storage.v2', "
                     "'careergps.skill_gap_run_storage.v3')")


def _now_column(**options) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, **options)


class SkillGapRunRecord(Base):
    """One Skill Gap analysis of one confirmed résumé for one role.

    Named *Record* to stay apart from the API schema `app.schemas.skill_gap_web.SkillGapRun`.
    """

    __tablename__ = "skill_gap_runs"
    __table_args__ = (
        CheckConstraint(f"job_family IN {_JOB_FAMILIES}", name="ck_skill_gap_runs_job_family"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_skill_gap_runs_status"),
        CheckConstraint(f"resume_hash {_SHA256}", name="ck_skill_gap_runs_resume_hash"),
        CheckConstraint(f"calculation_fingerprint {_SHA256}", name="ck_skill_gap_runs_calculation_fingerprint"),
        CheckConstraint(f"demand_snapshot_fingerprint {_SHA256}", name="ck_skill_gap_runs_demand_fingerprint"),
        CheckConstraint(f"instructions_sha256 IS NULL OR instructions_sha256 {_SHA256}",
                        name="ck_skill_gap_runs_instructions_sha256"),
        CheckConstraint("jsonb_typeof(reviewed_resume_snapshot) = 'object'", name="ck_skill_gap_runs_snapshot_object"),
        CheckConstraint("elapsed_seconds >= 0", name="ck_skill_gap_runs_elapsed_seconds"),
        CheckConstraint("model_calls >= 0", name="ck_skill_gap_runs_model_calls"),
        # A completed run has its report and finish time; any other run has no report.
        CheckConstraint(
            "CASE WHEN status = 'completed' THEN report IS NOT NULL AND jsonb_typeof(report) = 'object' "
            "AND completed_at IS NOT NULL AND error IS NULL ELSE report IS NULL END",
            name="ck_skill_gap_runs_completed_report"),
        CheckConstraint("status IN ('queued', 'running') OR completed_at IS NOT NULL",
                        name="ck_skill_gap_runs_completed_at"),
        CheckConstraint(f"storage_schema_version IN {_STORAGE_VERSIONS}",
                        name="ck_skill_gap_runs_storage_schema_version"),
        CheckConstraint("extraction_strategy IN ('single', 'skill_groups')", name="ck_skill_gap_runs_extraction_strategy"),
        CheckConstraint("match_score >= 0 AND match_score <= 1", name="ck_skill_gap_runs_match_score"),
        CheckConstraint("scored_skill_count >= 0 AND unscored_skill_count >= 0", name="ck_skill_gap_runs_skill_counts"),
        CheckConstraint("jsonb_typeof(extraction_audit) = 'object'", name="ck_skill_gap_runs_extraction_audit_object"),
        CheckConstraint("jsonb_typeof(timings) = 'object'", name="ck_skill_gap_runs_timings_object"),
        CheckConstraint("status = 'completed' OR match_score IS NULL", name="ck_skill_gap_runs_match_when_completed"),
        CheckConstraint(
            "storage_schema_version <> 'careergps.skill_gap_run_storage.v3' OR status <> 'completed' OR "
            "(scored_skill_count IS NOT NULL AND unscored_skill_count IS NOT NULL AND extraction_audit IS NOT NULL)",
            name="ck_skill_gap_runs_v3_completed"),
        # The résumé must belong to the same user; deleting it deletes its analyses.
        ForeignKeyConstraint(["resume_id", "user_id"], ["resumes.id", "resumes.user_id"],
                             name="fk_skill_gap_runs_resume", ondelete="CASCADE"),
        # Lets result rows prove they copy their run's owner and job family.
        UniqueConstraint("id", "user_id", "job_family", name="uq_skill_gap_runs_id_user_family"),
        # Latest run for a destination's résumé and configuration.
        Index("ix_skill_gap_runs_latest", "user_id", "resume_id", "job_family", "calculation_fingerprint", "created_at"),
        Index("ix_skill_gap_runs_user_id", "user_id"),
        # At most one queued/running (paid) run per résumé, role and configuration.
        Index("uq_skill_gap_runs_one_active", "user_id", "resume_id", "job_family", "calculation_fingerprint",
              unique=True, postgresql_where=text("status IN ('queued', 'running')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, **_UUID_DEFAULT)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    resume_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    job_family: Mapped[str] = mapped_column(Text, nullable=False)
    resume_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # The confirmed résumé exactly as analyzed: résumés can change, quotes must still resolve.
    reviewed_resume_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Configuration the result depends on; a change means the run is not reused.
    calculation_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    demand_snapshot_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    response_schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    catalog_version: Mapped[str | None] = mapped_column(Text)
    prompt_revision: Mapped[str | None] = mapped_column(Text)
    instructions_sha256: Mapped[str | None] = mapped_column(Text)
    response_processing_version: Mapped[str | None] = mapped_column(Text)
    # Single-Agent (v1) runs only; group runs keep their Agents in skill_gap_run_branches.
    agent_name: Mapped[str | None] = mapped_column(Text)
    agent_version: Mapped[str | None] = mapped_column(Text)
    # Progress and outcome.
    status: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[float] = mapped_column(Float, server_default=text("0"), nullable=False)
    model_calls: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict[str, Any] | None] = mapped_column(_NULLABLE_JSONB)
    # The merged answer of the three groups (or the single Agent's answer in v1).
    raw_agent_output: Mapped[Any] = mapped_column(_NULLABLE_JSONB, nullable=True)
    # Added by df5726089a8e (storage v3).
    storage_schema_version: Mapped[str] = mapped_column(
        Text, server_default=text(f"'{STORAGE_SCHEMA_VERSION}'"), nullable=False)
    resume_filename: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_strategy: Mapped[str | None] = mapped_column(Text)
    partition_policy_version: Mapped[str | None] = mapped_column(Text)
    selection_policy_version: Mapped[str | None] = mapped_column(Text)
    reuse_from_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skill_gap_runs.id", ondelete="SET NULL", name="fk_skill_gap_runs_reuse_from_run"))
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    scored_skill_count: Mapped[int | None] = mapped_column(SmallInteger)
    unscored_skill_count: Mapped[int | None] = mapped_column(SmallInteger)
    extraction_audit: Mapped[dict[str, Any] | None] = mapped_column(_NULLABLE_JSONB)
    timings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    def __repr__(self) -> str:
        return f"<SkillGapRunRecord {self.id} {self.job_family} {self.status}>"


class SkillGapRunBranch(Base):
    """One of the three skill-group Agents of a run, with its raw answer and checks."""

    __tablename__ = "skill_gap_run_branches"
    __table_args__ = (
        CheckConstraint(f"branch IN {_GROUPS}", name="ck_skill_gap_run_branches_branch"),
        CheckConstraint("status IN ('pending', 'ready', 'running', 'completed', 'failed', 'skipped_empty', "
                        "'not_started')", name="ck_skill_gap_run_branches_status"),
        CheckConstraint(f"input_sha256 {_SHA256}", name="ck_skill_gap_run_branches_input_sha256"),
        CheckConstraint("model_calls >= 0 AND model_calls <= 1", name="ck_skill_gap_run_branches_model_calls"),
        CheckConstraint("elapsed_seconds >= 0 AND inference_seconds >= 0", name="ck_skill_gap_run_branches_seconds"),
        CheckConstraint("input_tokens >= 0 AND cached_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0",
                        name="ck_skill_gap_run_branches_tokens"),
        CheckConstraint("jsonb_typeof(validation) = 'object' AND jsonb_typeof(response_processing) = 'object'",
                        name="ck_skill_gap_run_branches_checks_objects"),
        Index("ix_skill_gap_run_branches_input_sha256", "input_sha256"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skill_gap_runs.id", ondelete="CASCADE", name="fk_skill_gap_run_branches_run"), primary_key=True)
    branch: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(Text)
    agent_version: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    reasoning_effort: Mapped[str | None] = mapped_column(Text)
    # Hash of the exact group input; a later branch cache looks completed answers up by it.
    input_sha256: Mapped[str | None] = mapped_column(Text)
    reused: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skill_gap_runs.id", ondelete="SET NULL", name="fk_skill_gap_run_branches_source_run"))
    model_calls: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"), nullable=False)
    elapsed_seconds: Mapped[float] = mapped_column(Float, server_default=text("0"), nullable=False)
    inference_seconds: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[Any] = mapped_column(_NULLABLE_JSONB, nullable=True)
    validation: Mapped[dict[str, Any] | None] = mapped_column(_NULLABLE_JSONB)
    response_processing: Mapped[dict[str, Any] | None] = mapped_column(_NULLABLE_JSONB)
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = _now_column(onupdate=func.now())

    def __repr__(self) -> str:
        return f"<SkillGapRunBranch {self.run_id} {self.branch} {self.status}>"


class SkillGapResult(Base):
    """One core skill of a completed run: the report's skill row flattened for queries, plus its evidence."""

    __tablename__ = "skill_gap_results"
    __table_args__ = (
        CheckConstraint(f"job_family IN {_JOB_FAMILIES}", name="ck_skill_gap_results_job_family"),
        CheckConstraint("position >= 0", name="ck_skill_gap_results_position"),
        CheckConstraint(f"branch IN {_GROUPS}", name="ck_skill_gap_results_branch"),
        CheckConstraint("evidence_kind IN ('absent', 'knowledge', 'practice', 'limited_practice', 'uncertain')",
                        name="ck_skill_gap_results_evidence_kind"),
        CheckConstraint("calculation_state IN ('scored', 'needs_confirmation')",
                        name="ck_skill_gap_results_calculation_state"),
        CheckConstraint("evidence_strength >= 0 AND evidence_strength <= 1 AND skill_gap >= 0 AND skill_gap <= 1",
                        name="ck_skill_gap_results_scores"),
        CheckConstraint("grade IN ('A', 'A-', 'B+', 'B', 'C', 'D', 'F')", name="ck_skill_gap_results_grade"),
        CheckConstraint("demand_required_count >= 0 AND demand_preferred_only_count >= 0 AND "
                        "demand_unspecified_count >= 0 AND demand_n > 0", name="ck_skill_gap_results_demand"),
        CheckConstraint("demand_weight >= 0 AND demand_weight <= 1 AND priority >= 0 AND priority <= 1",
                        name="ck_skill_gap_results_weights"),
        CheckConstraint("priority_rank >= 1", name="ck_skill_gap_results_priority_rank"),
        # A scored skill has all its numbers; one that needs confirmation has none and no rank.
        CheckConstraint(
            "CASE WHEN calculation_state = 'scored' THEN evidence_strength IS NOT NULL AND skill_gap IS NOT NULL "
            "AND grade IS NOT NULL AND priority IS NOT NULL ELSE evidence_strength IS NULL AND skill_gap IS NULL "
            "AND grade IS NULL AND priority IS NULL AND priority_rank IS NULL END",
            name="ck_skill_gap_results_scored_values"),
        CheckConstraint("jsonb_typeof(agent_assessment) = 'object' AND jsonb_typeof(scoring_breakdown) = 'object' "
                        "AND jsonb_typeof(reference_check) = 'object' AND jsonb_typeof(merge_audit) = 'object'",
                        name="ck_skill_gap_results_details_objects"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="ck_skill_gap_results_evidence_array"),
        # The run's owner and job family; deleting the run (or its résumé) deletes its results.
        ForeignKeyConstraint(["run_id", "user_id", "job_family"],
                             ["skill_gap_runs.id", "skill_gap_runs.user_id", "skill_gap_runs.job_family"],
                             name="fk_skill_gap_results_run", ondelete="CASCADE"),
        UniqueConstraint("run_id", "position", name="uq_skill_gap_results_position"),
        UniqueConstraint("run_id", "priority_rank", name="uq_skill_gap_results_priority_rank"),
        # Other agents and analytics: one skill across a user's runs or across users of a role.
        Index("ix_skill_gap_results_user_family_skill", "user_id", "job_family", "skill_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    skill_id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Copied from the run (enforced by the composite FK) so queries across users need no join.
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    job_family: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    module_id: Mapped[str] = mapped_column(Text, nullable=False)
    module_name: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str | None] = mapped_column(Text)
    evidence_kind: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_state: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_strength: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    skill_gap: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    grade: Mapped[str | None] = mapped_column(Text)
    demand_required_count: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_preferred_only_count: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_unspecified_count: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_n: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_weight: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    priority: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    # 1 = the gap to work on first (the report's priority_order).
    priority_rank: Mapped[int | None] = mapped_column(SmallInteger)
    agent_assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    original_agent_assessment: Mapped[dict[str, Any] | None] = mapped_column(_NULLABLE_JSONB)
    scoring_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reference_check: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    merge_audit: Mapped[dict[str, Any] | None] = mapped_column(_NULLABLE_JSONB)
    # One item per quoted proof: role, unit_id, activity_id, source_path, quote, start, end.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = _now_column()

    def __repr__(self) -> str:
        return f"<SkillGapResult {self.run_id} {self.skill_id} {self.calculation_state}>"
