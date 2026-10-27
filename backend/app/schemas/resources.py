from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.skill_gap_web import JobFamily

ResourceType = Literal["student_org", "certification", "online_course", "school_course", "project"]
PlanStatus = Literal["saved", "done"]


class Resource(BaseModel):
    id: str
    type: ResourceType
    title: str
    provider: str
    meta: str
    description: str
    # Only the skills in the requested role's catalog.
    skills: list[str]
    url: str | None = None
    school: str | None = None
    alongside: bool = False


class ResourceList(BaseModel):
    job_family: JobFamily
    resources: list[Resource]


class PlanItem(BaseModel):
    resource_id: str
    status: PlanStatus
    saved_at: str
    done_at: str | None = None


class Plan(BaseModel):
    """Saved resources for one role. The order is chosen in the browser from the gap ranking."""

    job_family: JobFamily
    items: list[PlanItem]


class PlanItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_family: JobFamily
    status: PlanStatus = "saved"


# Project recommendations from the resources agent (app/services/resources_agent.py).


class ProjectRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    addressed_gaps: list[str] = Field(min_length=1)
    why_recommended: str = Field(min_length=1)
    prerequisites_to_check: list[str]


class ResourceRecommendations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[ProjectRecommendation] = Field(max_length=3)
    no_match_reason: str | None

    @model_validator(mode="after")
    def check_reason(self):
        if self.recommendations and self.no_match_reason is not None:
            raise ValueError("Recommendations must have a null no_match_reason.")
        if not self.recommendations and (
            not self.no_match_reason or not self.no_match_reason.strip()
        ):
            raise ValueError("Empty recommendations require a reason.")
        return self
