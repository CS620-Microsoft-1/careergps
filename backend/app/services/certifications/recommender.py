"""Recommend certifications for a completed Skill Gap run by matching catalog skills to its gaps.

No model call and nothing cached: ranking.rank() picks from the current catalog on every request.
"""
from datetime import datetime, timezone
from functools import lru_cache

from app.schemas.certifications import CertificationRecommendations
from app.schemas.skill_gap_web import SkillGapRun
from .catalog import for_family, get_catalog
from .ranking import rank, top_gaps


class CertificationRecommender:
    def __init__(self, *, catalog: dict | None = None) -> None:
        # None: read the current catalog on every call, so database changes show up without a restart.
        self._catalog = catalog

    @property
    def catalog(self) -> dict:
        return self._catalog if self._catalog is not None else get_catalog()

    def recommend(self, run: SkillGapRun) -> CertificationRecommendations:
        if run.status != "completed" or run.report is None:
            raise ValueError("The skill gap analysis has not completed")
        family = run.job_family
        picks = rank(for_family(self.catalog, family), family, top_gaps(run.report))
        return CertificationRecommendations(job_family=family, skill_gap_run_id=run.id,
                                            generated_at=datetime.now(timezone.utc).isoformat(),
                                            recommendations=picks)


@lru_cache(maxsize=1)
def get_certification_recommender() -> CertificationRecommender:
    return CertificationRecommender()
