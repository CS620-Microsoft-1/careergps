from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.resources_agent import recommend_projects


router = APIRouter(prefix="/resources", tags=["resources"])


class ResourceRequest(BaseModel):
    career_path: str = Field(min_length=1)
    existing_skills: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    available_hours: int | None = Field(default=None, gt=0)


@router.post("/projects")
def get_project_recommendations(request: ResourceRequest):
    try:
        return recommend_projects(
            career_path=request.career_path,
            existing_skills=request.existing_skills,
            skill_gaps=request.skill_gaps,
            available_hours=request.available_hours,
        )
    except Exception:
        # Avoid exposing account or service details in the API response.
        raise HTTPException(
            status_code=500,
            detail="Could not generate project recommendations.",
        ) from None