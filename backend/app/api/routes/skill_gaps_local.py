"""Local-only web routes. Mount only in app.local_main, never the shared DB app."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.skill_gap_web import JobFamily, MarketDemandSnapshot, SkillGapRun, SkillGapRunRequest
from app.services.skill_gap_market import get_market_demand
from app.services.skill_gap_web import SkillGapRunManager, get_skill_gap_run_manager

router = APIRouter(prefix="/skill-gaps", tags=["local-skill-gaps"])


@router.get("/market/{family}", response_model=MarketDemandSnapshot)
def market_demand(family: JobFamily) -> MarketDemandSnapshot:
    try:
        return MarketDemandSnapshot.model_validate(get_market_demand(family))
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=503, detail="The local market snapshot is unavailable.") from None


@router.post("/runs", response_model=SkillGapRun, status_code=status.HTTP_202_ACCEPTED)
def start_run(request: SkillGapRunRequest,
              manager: SkillGapRunManager = Depends(get_skill_gap_run_manager)) -> SkillGapRun:
    try:
        return manager.submit(request)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=503, detail="Local analysis storage or queue is unavailable.") from None


@router.get("/runs/{identifier}", response_model=SkillGapRun)
def get_run(identifier: str, manager: SkillGapRunManager = Depends(get_skill_gap_run_manager)) -> SkillGapRun:
    try:
        return manager.get(identifier)
    except KeyError:
        raise HTTPException(status_code=404, detail="Analysis run not found.") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Local analysis result is unavailable.") from None
