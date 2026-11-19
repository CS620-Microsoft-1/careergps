"""Suggested action plans for the latest Skill Gap run of a direction (action-plan-agent or the rule plan)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_account_service, get_current_db_user, get_db
from app.api.routes.skill_gaps import _saved_resume
from app.models import User
from app.schemas.action_plans import ActionPlanRequest, ActionPlanSuggestions
from app.services.accounts import AccountService
from app.services.action_plans.planner import ActionPlanner, get_action_planner
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from app.services.skill_gaps.transport import SkillGapConfigurationError
from app.services.student_courses import list_taken

router = APIRouter(prefix="/action-plans", tags=["action-plans"])


@router.post("/suggestions", response_model=ActionPlanSuggestions)
def suggestions(request: ActionPlanRequest,
                user: User = Depends(get_current_db_user),
                db: Session = Depends(get_db),
                accounts: AccountService = Depends(get_account_service),
                runs: SkillGapRunManager = Depends(get_skill_gap_run_manager),
                store: LocalPlanStore = Depends(get_plan_store),
                planner: ActionPlanner = Depends(get_action_planner),
                ) -> ActionPlanSuggestions:
    saved = _saved_resume(user, accounts, request.job_family)
    try:
        run = runs.latest(user_id=saved.user_id, resume_id=saved.resume_id,
                          reviewed_resume=saved.reviewed_resume, job_family=saved.job_family)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run a skill gap analysis for this direction first") from None
    except SkillGapConfigurationError as error:
        raise HTTPException(status_code=503, detail=error.public_message) from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable") from None
    if run.status == "failed":
        raise HTTPException(status_code=409, detail="The latest skill gap analysis failed. Run it again")
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="The skill gap analysis has not finished yet")

    # What the student already finished never comes back as a suggestion.
    try:
        taken = {course.course_id for course in list_taken(db, user.id)}
        done = {item["resource_id"] for item in store.items(user.id, request.job_family) if item["status"] == "done"}
    except (SQLAlchemyError, OSError):
        raise HTTPException(status_code=503, detail="Action plans are unavailable") from None
    accounts.end_reads()  # the Agent call can take a while; don't hold a pooled connection

    try:
        return planner.suggest(run, mode=request.mode, university=user.university,
                               taken_course_ids=taken, done_resource_ids=done)
    except OSError:
        raise HTTPException(status_code=503, detail="Action plans are unavailable") from None
