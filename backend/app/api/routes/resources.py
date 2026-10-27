"""Resources that close skill gaps, and the student's saved plan for each role."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_db_user
from app.models import User
from app.schemas.resources import Plan, PlanItem, PlanItemUpdate, ResourceList
from app.schemas.skill_gap_web import JobFamily
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.resources import resources_for

router = APIRouter(tags=["resources"])


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
