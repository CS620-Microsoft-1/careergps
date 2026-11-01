"""Authenticated Skill Gaps: saved database resume in, local JSON results out."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.api.deps import get_account_service, get_current_db_user, get_current_user
from app.core.security import AuthenticatedUser
from app.models import User
from app.schemas.resume import ResumeClassification
from app.schemas.skill_gap_web import JobFamily, MarketDemandSnapshot, SkillGapRun, SkillGapRunRequest
from app.services.accounts import AccountService, role_family
from app.services.skill_gaps.market import get_market_demand
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager

router = APIRouter(prefix="/skill-gaps", tags=["skill-gaps"])


@dataclass(frozen=True)
class SavedResume:
    """Detached request snapshot: background work never holds an ORM session."""
    user_id: UUID
    resume_id: UUID
    filename: str
    confirmed_at: datetime
    reviewed_resume: dict
    job_family: JobFamily


def _saved_resume(user: User, accounts: AccountService, selected: JobFamily | None) -> SavedResume:
    """The résumé of the selected destination, or of the account's target role by default."""
    family = selected or role_family(user.target_role)
    if family is None:
        raise HTTPException(status_code=422, detail="Choose a supported target role before analysis")
    resume = accounts.get_resume(user, family)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="No confirmed resume saved for this account")
    try:
        reviewed = ResumeClassification.model_validate(deepcopy(resume.confirmed_data)).model_dump(mode="json")
    except (ValidationError, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="The saved resume needs to be reviewed and saved again") from None
    accounts.end_reads()  # the callers' Agent work runs without an open transaction
    return SavedResume(user.id, resume.id, resume.original_filename, resume.created_at, reviewed, family)


@router.get("/market/{family}", response_model=MarketDemandSnapshot)
def market_demand(family: JobFamily, user: AuthenticatedUser = Depends(get_current_user)) -> MarketDemandSnapshot:
    """Not user-specific, so onboarding can show it before the account row exists."""
    try:
        return MarketDemandSnapshot.model_validate(get_market_demand(family))
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=503, detail="The market demand snapshot is unavailable") from None


@router.post("/runs", response_model=SkillGapRun, status_code=status.HTTP_202_ACCEPTED)
def start_run(request: SkillGapRunRequest,
              user: User = Depends(get_current_db_user),
              accounts: AccountService = Depends(get_account_service),
              manager: SkillGapRunManager = Depends(get_skill_gap_run_manager)) -> SkillGapRun:
    saved = _saved_resume(user, accounts, request.job_family)
    try:
        return manager.submit(user_id=saved.user_id, resume_id=saved.resume_id,
            reviewed_resume=saved.reviewed_resume, filename=saved.filename, confirmed_at=saved.confirmed_at,
            job_family=saved.job_family, force=request.force)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=503, detail="Analysis storage or queue is unavailable") from None


@router.get("/runs/latest", response_model=SkillGapRun)
def latest_run(job_family: JobFamily | None = None,
               user: User = Depends(get_current_db_user),
               accounts: AccountService = Depends(get_account_service),
               manager: SkillGapRunManager = Depends(get_skill_gap_run_manager)) -> SkillGapRun:
    saved = _saved_resume(user, accounts, job_family)
    try:
        return manager.latest(user_id=saved.user_id, resume_id=saved.resume_id,
            reviewed_resume=saved.reviewed_resume, job_family=saved.job_family)
    except KeyError:
        raise HTTPException(status_code=404, detail="No analysis for this role's résumé") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable") from None


@router.get("/runs/{identifier}", response_model=SkillGapRun)
def get_run(identifier: str, user: User = Depends(get_current_db_user),
            manager: SkillGapRunManager = Depends(get_skill_gap_run_manager)) -> SkillGapRun:
    try:
        return manager.get(identifier, user_id=user.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Analysis run not found") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable") from None
