from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.resources_agent import recommend_projects
from app.api.routes.skill_gaps import SavedResume, get_saved_resume
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from fastapi import Depends
import json
from app.services.skill_gaps.assets import ASSET_ROOT


router = APIRouter(prefix="/resources", tags=["resources"])


class ResourceRequest(BaseModel):
    career_path: str = Field(min_length=1)
    existing_skills: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    available_hours: int | None = Field(default=None, gt=0)


class RunProjectRequest(BaseModel):
    run_id: str = Field(min_length=1)
    available_hours: int | None = Field(default=None, gt=0)


FAMILY_TO_CATALOG = {
    "software_engineer": "Software Engineering",
    "data_analyst": "Data Analyst",
    "ai_engineer": "AI/ML Engineering",
}


def inputs_from_report(report: dict, family: str) -> dict:
    """Use only ranked, scored gaps; missing evidence is not an existing skill."""
    if report.get("job_family") != family or family not in FAMILY_TO_CATALOG:
        raise ValueError("Unsupported or inconsistent career family.")
    skills = report.get("skills")
    priority_order = report.get("priority_order")
    if not isinstance(skills, list) or not isinstance(priority_order, list):
        raise ValueError("Invalid skill-gap report.")
    by_id = {item["skill_id"]: item for item in skills if isinstance(item, dict) and isinstance(item.get("skill_id"), str)}
    catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    definitions = {skill["skill_id"]: skill for module in catalog["families"][family]["modules"] for skill in module["skills"]}
    gaps = []
    verified_skill_gaps = []
    for identifier in priority_order:
        item = by_id.get(identifier)
        if not item or item.get("calculation_state") != "scored":
            continue
        gap, name = item.get("skill_gap"), item.get("skill_name")
        definition = definitions.get(identifier)
        if isinstance(gap, (int, float)) and not isinstance(gap, bool) and gap > 0 and definition and name == definition["skill_name"] and name not in gaps:
            gaps.append(name)
            verified_skill_gaps.append({"skill_id": identifier, "skill_name": name, "definition": definition["definition"]})
    return {"career_path": FAMILY_TO_CATALOG[family], "existing_skills": [], "skill_gaps": gaps, "verified_skill_gaps": verified_skill_gaps}


@router.post("/projects/from-skill-gap")
def projects_from_skill_gap(
    request: RunProjectRequest,
    saved: SavedResume = Depends(get_saved_resume),
    manager: SkillGapRunManager = Depends(get_skill_gap_run_manager),
):
    try:
        run = manager.get(request.run_id, user_id=saved.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Analysis run not found.") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable.") from None
    if run.resume_id != saved.resume_id:
        raise HTTPException(status_code=409, detail="Analysis is not for the active resume.")
    if run.status != "completed" or not isinstance(run.report, dict):
        raise HTTPException(status_code=409, detail="Skill-gap analysis is not complete.")
    try:
        inputs = inputs_from_report(run.report, run.job_family)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail="Skill-gap report cannot be used for recommendations.") from None
    if not inputs["skill_gaps"]:
        return {"recommendations": [], "no_match_reason": "No scored skill gaps are available for this analysis."}
    try:
        return recommend_projects(**inputs, available_hours=request.available_hours)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not generate project recommendations.") from None


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
