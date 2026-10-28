"""Resources that close skill gaps, the student's saved plan for each role, and project
recommendations from the resources agent."""
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_account_service, get_current_db_user
from app.core.config import BACKEND_ROOT, get_settings
from app.models import User
from app.schemas.resources import Plan, PlanItem, PlanItemUpdate, ResourceList
from app.schemas.skill_gap_web import JobFamily
from app.services.accounts import AccountService
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.resources import FAMILY_TO_CATALOG, resources_for
from app.services.resources_agent import rank_projects, recommend_projects
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from app.services.skill_gaps.storage import load, save_json

router = APIRouter(tags=["resources"])
logger = logging.getLogger(__name__)

# Agent picks per completed run, so a page visit doesn't pay for another model call.
PROJECT_PICKS_DIR = BACKEND_ROOT / "local_results" / "project_recommendations"
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


@router.get("/resources", response_model=ResourceList)
def list_resources(job_family: JobFamily, user: User = Depends(get_current_db_user)) -> ResourceList:
    return ResourceList(job_family=job_family, resources=resources_for(job_family, user.university))


@router.get("/plan", response_model=Plan)
def read_plan(job_family: JobFamily, user: User = Depends(get_current_db_user),
              store: LocalPlanStore = Depends(get_plan_store)) -> Plan:
    # Hide saves for resources that left the catalog or belong to another school.
    available = {entry["id"] for entry in resources_for(job_family, user.university)}
    items = [item for item in store.items(user.id, job_family) if item["resource_id"] in available]
    return Plan(job_family=job_family, items=items)


@router.put("/plan/items/{resource_id}", response_model=PlanItem)
def save_plan_item(resource_id: str, data: PlanItemUpdate, user: User = Depends(get_current_db_user),
                   store: LocalPlanStore = Depends(get_plan_store)) -> PlanItem:
    """Save a resource to the plan, or mark it done ("done") or not done ("saved")."""
    if resource_id not in {entry["id"] for entry in resources_for(data.job_family, user.university)}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found for this role")
    try:
        return PlanItem.model_validate(store.set_status(user.id, data.job_family, resource_id, data.status))
    except OSError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Plan storage is unavailable") from None


@router.delete("/plan/items/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_plan_item(resource_id: str, job_family: JobFamily, user: User = Depends(get_current_db_user),
                     store: LocalPlanStore = Depends(get_plan_store)) -> None:
    try:
        store.remove(user.id, job_family, resource_id)
    except OSError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Plan storage is unavailable") from None


class ResourceRequest(BaseModel):
    career_path: str = Field(min_length=1)
    existing_skills: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    available_hours: int | None = Field(default=None, gt=0)


class RunProjectRequest(BaseModel):
    run_id: str = Field(min_length=1)
    available_hours: int | None = Field(default=None, gt=0)




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


@router.post("/resources/projects/from-skill-gap")
def projects_from_skill_gap(
    request: RunProjectRequest,
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
    manager: SkillGapRunManager = Depends(get_skill_gap_run_manager),
):
    try:
        run = manager.get(request.run_id, user_id=user.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Analysis run not found.") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable.") from None
    # The run must be for the résumé its role uses now.
    resume = accounts.get_resume(user, run.job_family)
    if resume is None or run.resume_id != resume.id:
        raise HTTPException(status_code=409, detail="Analysis is not for this role's current resume.")
    if run.status != "completed" or not isinstance(run.report, dict):
        raise HTTPException(status_code=409, detail="Skill-gap analysis is not complete.")
    accounts.end_reads()  # the resources Agent can take tens of seconds; don't hold a transaction
    try:
        inputs = inputs_from_report(run.report, run.job_family)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail="Skill-gap report cannot be used for recommendations.") from None
    if not inputs["skill_gaps"]:
        return {"recommendations": [], "no_match_reason": "No scored skill gaps are available for this analysis.",
                "source": "rules"}
    # Only the default (no time budget) answer is cached; the rule fallback is free and never cached.
    cache = PROJECT_PICKS_DIR / f"{run.id}.json" if request.available_hours is None and _RUN_ID.fullmatch(str(run.id)) else None
    if cache is not None and cache.exists():
        return load(cache)
    if get_settings().resources_project_endpoint:
        try:
            result = {**recommend_projects(**inputs, available_hours=request.available_hours), "source": "agent"}
        except Exception as error:
            logger.warning("Resources agent failed (%s); using gap ranking", type(error).__name__)
        else:
            if cache is not None:
                save_json(cache, result)
            return result
    return {**rank_projects(**inputs, available_hours=request.available_hours), "source": "rules"}


@router.post("/resources/projects")
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
