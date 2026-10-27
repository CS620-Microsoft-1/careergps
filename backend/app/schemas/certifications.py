"""Certification catalog and recommendation contract for the Resources page."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.skill_gap_web import JobFamily


class Certification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    provider: str
    url: str
    # None when the price depends on a subscription or is not published.
    cost_usd: float | None = Field(ge=0)
    cost_note: str
    level: Literal["beginner", "intermediate", "advanced"]
    # Core skill ids per job family; the same concept can have different ids per family.
    skills: dict[JobFamily, list[str]]
    last_verified: str


class CertificationCatalog(BaseModel):
    job_family: JobFamily
    version: str
    certifications: list[Certification]


class CertificationRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_family: JobFamily | None = None


class CertificationRecommendation(BaseModel):
    certification_id: str
    # The user's gap skills this certification covers.
    skill_ids: list[str]
    reason: str | None


class CertificationRecommendations(BaseModel):
    job_family: JobFamily
    skill_gap_run_id: str
    # "rules" when the Agent is not configured or failed; reasons are then empty.
    source: Literal["agent", "rules"]
    generated_at: str
    recommendations: list[CertificationRecommendation]
