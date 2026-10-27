"""Local web contract. Scores and demand are always selected by the server."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


JobFamily = Literal["software_engineer", "data_analyst", "ai_engineer"]


class SkillGapRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The authenticated backend loads the confirmed resume; never accept a
    # browser-supplied snapshot or an asserted confirmation flag.
    job_family: JobFamily | None = None
    force: bool = False


class SkillGapMatch(BaseModel):
    """Demand-weighted résumé evidence (app/services/skill_gaps/match.py); uncalibrated."""

    score: float = Field(ge=0, le=1)
    scored_skill_count: int = Field(ge=0)
    unscored_skill_count: int = Field(ge=0)


class SkillGapRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: UUID
    resume_id: UUID
    status: Literal["queued", "running", "completed", "failed"]
    phase: str
    job_family: JobFamily
    filename: str
    resume_hash: str
    created_at: str
    completed_at: str | None
    elapsed_seconds: float
    model_calls: int
    report: dict[str, Any] | None
    error: str | None
    reused: bool = False
    match: SkillGapMatch | None = None


class MarketDemandSkill(BaseModel):
    skill_id: str
    module_id: str
    N: int = Field(gt=0)
    required_job_count: int = Field(ge=0)
    preferred_only_job_count: int = Field(ge=0)
    unspecified_job_count: int = Field(ge=0)
    required_ratio: float = Field(ge=0, le=1)
    preferred_only_ratio: float = Field(ge=0, le=1)
    unspecified_ratio: float = Field(ge=0, le=1)


class MarketDemandSnapshot(BaseModel):
    job_family: JobFamily
    sample_size: int = Field(gt=0)
    core_skill_count: int = Field(gt=0)
    source_analysis_version: str
    snapshot_fingerprint: str
    snapshot_generated_at: str
    source_description: str
    posting_window: str | None = None
    company_coverage: int | None = Field(default=None, ge=0)
    coverage_limitations: list[str]
    skills: list[MarketDemandSkill]
    responsibilities_available: Literal[False] = False
    common_responsibilities: list[str] = Field(default_factory=list, max_length=0)
    database_used: Literal[False] = False
