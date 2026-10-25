"""Local web contract. Scores and demand are always selected by the server."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.schemas.resume import ResumeClassification

JobFamily = Literal["software_engineer", "data_analyst", "ai_engineer"]


class SkillGapRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: StrictBool
    reviewed_resume: ResumeClassification
    job_family: JobFamily
    filename: str = Field(min_length=1, max_length=255)
    confirmed_at: datetime
    force: bool = False

    @field_validator("confirmed")
    @classmethod
    def must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Review and confirm the resume before analysis")
        return value

    @field_validator("filename")
    @classmethod
    def nonempty_filename(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A resume filename is required")
        return value.strip()

    @field_validator("confirmed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Confirmation time must include a timezone")
        return value


class SkillGapRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
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
    skills: list[MarketDemandSkill]
    responsibilities_available: Literal[False] = False
    common_responsibilities: list[str] = Field(default_factory=list, max_length=0)
    database_used: Literal[False] = False
