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
    # School courses from the course guide: "COMP SCI 400", "3", "Fall 2025".
    course_code: str | None = None
    credits: str | None = None
    last_taught: str | None = None


class ResourceList(BaseModel):
    job_family: JobFamily
    resources: list[Resource]


class PlanItem(BaseModel):
    resource_id: str
    status: PlanStatus
    saved_at: str
    done_at: str | None = None
    # Place in a suggested action plan (1 = first step). None: ordered by the gap ranking.
    position: int | None = None


class Plan(BaseModel):
    """Saved resources for one role. The browser orders them by position when set, else by the gap ranking."""

    job_family: JobFamily
    items: list[PlanItem]


class PlanItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_family: JobFamily
    status: PlanStatus = "saved"


class SuggestedPlanSave(BaseModel):
    """A suggested action plan added as a whole ("Add all"). steps are in order and get positions 1..n;
    alongside items are saved without one. Every other saved item loses its position."""

    model_config = ConfigDict(extra="forbid")

    job_family: JobFamily
    steps: list[str] = Field(min_length=1)
    alongside: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> "SuggestedPlanSave":
        ids = [*self.steps, *self.alongside]
        if len(ids) != len(set(ids)):
            raise ValueError("A resource can appear only once in a suggested plan")
        return self


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
