"""Certification catalog per job family and recommendations from the latest Skill Gap run."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_account_service, get_current_db_user
from app.api.routes.skill_gaps import _saved_resume
from app.models import User
from app.schemas.certifications import (
    CertificationCatalog, CertificationRecommendationRequest, CertificationRecommendations,
)
from app.schemas.skill_gap_web import JobFamily
from app.services.accounts import AccountService
from app.services.certifications.catalog import for_family
from app.services.certifications.recommender import CertificationRecommender, get_certification_recommender
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager

router = APIRouter(prefix="/certifications", tags=["certifications"])


@router.get("/catalog/{family}", response_model=CertificationCatalog)
def catalog(family: JobFamily, user: User = Depends(get_current_db_user),
            recommender: CertificationRecommender = Depends(get_certification_recommender)) -> CertificationCatalog:
    return CertificationCatalog(job_family=family, version=recommender.catalog["version"],
                                certifications=for_family(recommender.catalog, family))


@router.post("/recommendations", response_model=CertificationRecommendations)
def recommendations(request: CertificationRecommendationRequest,
                    user: User = Depends(get_current_db_user),
                    accounts: AccountService = Depends(get_account_service),
                    runs: SkillGapRunManager = Depends(get_skill_gap_run_manager),
                    recommender: CertificationRecommender = Depends(get_certification_recommender),
                    ) -> CertificationRecommendations:
    saved = _saved_resume(user, accounts, request.job_family)
    try:
        run = runs.latest(user_id=saved.user_id, resume_id=saved.resume_id,
                          reviewed_resume=saved.reviewed_resume, job_family=saved.job_family)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run a skill gap analysis for this direction first") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable") from None
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="The skill gap analysis has not finished yet")
    try:
        return recommender.recommend(run)
    except OSError:
        raise HTTPException(status_code=503, detail="Recommendations are unavailable") from None
