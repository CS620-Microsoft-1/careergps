"""Recommend certifications for a completed Skill Gap run, cached per run as local JSON.

Only Agent results are cached: the rule fallback is free, and caching it would hide
the Agent once it is configured. Agent picks outside the catalog are dropped.
"""
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Callable

from app.core.config import BACKEND_ROOT
from app.schemas.certifications import CertificationRecommendation, CertificationRecommendations
from app.schemas.skill_gap_web import SkillGapRun
from app.services.skill_gaps.storage import load, save_json
from . import agent
from .catalog import for_family, get_catalog
from .ranking import MAX_RECOMMENDATIONS, rank, top_gaps

logger = logging.getLogger(__name__)
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


class CertificationRecommender:
    def __init__(self, directory: Path | None = None, *, catalog: dict | None = None,
                 invoker: Callable[[dict], dict] | None = None,
                 configured: Callable[[], bool] | None = None) -> None:
        self.directory = (directory or BACKEND_ROOT / "local_results" / "certifications").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog or get_catalog()
        self._invoke = invoker or agent.invoke
        self._configured = configured or agent.is_configured
        self._locks: defaultdict[str, Lock] = defaultdict(Lock)
        self._locks_guard = Lock()

    def _cache_path(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("Unexpected run id")
        return self.directory / f"{run_id}.json"

    def recommend(self, run: SkillGapRun) -> CertificationRecommendations:
        if run.status != "completed" or run.report is None:
            raise ValueError("The skill gap analysis has not completed")
        path = self._cache_path(run.id)
        with self._locks_guard:
            lock = self._locks[run.id]
        # One Agent call per run, even when the page asks twice at once.
        with lock:
            if path.exists():
                cached = _Stored.model_validate(load(path))
                if cached.catalog_version == self.catalog["version"]:
                    return cached.public()
            result = self._generate(run)
            if result.source == "agent":
                save_json(path, result.model_dump(mode="json"))
            return result.public()

    def _generate(self, run: SkillGapRun) -> "_Stored":
        family = run.job_family
        certifications = for_family(self.catalog, family)
        gaps = top_gaps(run.report)
        picks, source = None, "rules"
        if gaps and certifications and self._configured():
            payload = {"job_family": family, "gaps": gaps, "catalog": [
                {"certification_id": item.id, "name": item.name, "provider": item.provider,
                 "level": item.level, "cost_usd": item.cost_usd, "cost_note": item.cost_note,
                 "skill_ids": item.skills[family]} for item in certifications]}
            try:
                picks = self._checked(self._invoke(payload), certifications, family, gaps)
                source = "agent"
            except Exception as error:
                # Keep SDK details in the server log; the page still gets rule-based picks.
                logger.warning("Certification Agent failed (%s); using gap ranking", type(error).__name__)
        if picks is None:
            picks = rank(certifications, family, gaps)
        return _Stored(job_family=family, skill_gap_run_id=run.id, source=source,
                       generated_at=datetime.now(timezone.utc).isoformat(), recommendations=picks,
                       catalog_version=self.catalog["version"])

    @staticmethod
    def _checked(output: dict, certifications: list, family: str, gaps: list[dict]) -> list[CertificationRecommendation]:
        """Keep only catalog certifications and gap skills each one really covers."""
        by_id = {item.id: item for item in certifications}
        gap_ids = {gap["skill_id"] for gap in gaps}
        picks, seen = [], set()
        for item in output["recommendations"]:
            certification = by_id.get(item["certification_id"])
            if certification is None or certification.id in seen:
                continue
            skill_ids = [skill for skill in dict.fromkeys(item["skill_ids"])
                         if skill in gap_ids and skill in certification.skills[family]]
            if not skill_ids:
                continue
            reason = item["reason"].strip() or None
            picks.append(CertificationRecommendation(certification_id=certification.id,
                                                     skill_ids=skill_ids, reason=reason))
            seen.add(certification.id)
        if not picks and output["recommendations"]:
            raise ValueError("No Agent pick matched the catalog")
        return picks[:MAX_RECOMMENDATIONS]


class _Stored(CertificationRecommendations):
    """Cache record: also remembers which catalog version the picks came from."""
    catalog_version: str

    def public(self) -> CertificationRecommendations:
        return CertificationRecommendations.model_validate(self.model_dump(exclude={"catalog_version"}))


_manager_lock = Lock()


@lru_cache(maxsize=1)
def _cached_recommender() -> CertificationRecommender:
    return CertificationRecommender()


def get_certification_recommender() -> CertificationRecommender:
    with _manager_lock:
        return _cached_recommender()
