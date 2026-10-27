from typing import Literal

from pydantic import BaseModel, ConfigDict

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
