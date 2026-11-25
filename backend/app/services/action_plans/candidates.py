"""The action plan Agent's input: the student's top gaps and the only resources it may use.

The candidates are the specialist recommenders' own shortlists, not the whole catalog:
- projects: the project Agent's shortlist (resources_agent._candidates), its picks ranked first;
- certifications: the role's certification catalog (certifications.catalog.for_family), the Resources page's
  skill-match picks (certifications.ranking.rank) first;
- school courses, online courses and clubs: the Resources page list (resources.resources_for); no Agent
  picks these.
Project Agent picks come from its per-run cache; when it is missing, the free rule ranking stands in. No
specialist Agent is called here. When the project Agent's shortlist changes, this follows it.

load_sources() reads the catalogs and caches; build_candidates() and agent_payload() are pure.
"""
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re

from app.core.config import BACKEND_ROOT
from app.schemas.certifications import Certification
from app.services.certifications.catalog import for_family, get_catalog
from app.services.certifications.ranking import rank as rank_certifications, top_gaps
from app.services.resources import FAMILY_TO_CATALOG, resources_for
from app.services.resources_agent import _candidates as project_shortlist, rank_projects

logger = logging.getLogger(__name__)

LOCAL_RESULTS = BACKEND_ROOT / "local_results"
PROJECT_CAP, CERTIFICATION_CAP, OTHER_CAP = 20, 12, 8
CATALOG_TYPES = ("school_course", "online_course", "student_org")
# "Prefer the right difficulty over the impressive one": on a tie, easier first.
_DIFFICULTY_ORDER = {"beginner": 0, "intermediate": 1, None: 1, "advanced": 2}
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class Picks:
    ids: tuple[str, ...]
    # "project_agent" from that Agent's cache, else "rules".
    source: str


@dataclass(frozen=True)
class Sources:
    resources: list[dict]               # resources_for(): card data for every type
    projects: list[dict]                # the project Agent's shortlist
    certifications: list[Certification]  # the role's certification catalog
    project_picks: Picks
    certification_picks: Picks


@dataclass(frozen=True)
class Candidates:
    items: list[dict]                   # INPUT_JSON candidates, best first within each type
    resources: dict[str, dict]          # resource_id -> card, for the API response


def gaps_from_report(report: dict) -> list[dict]:
    """The top scored gaps, highest priority first (priority is kept for the rule rankings only)."""
    return top_gaps(report)


def cached_project_picks(run_id: str, directory: Path = LOCAL_RESULTS) -> tuple[str, ...]:
    """IDs the project Agent picked for this run (local_results/project_recommendations), or ()."""
    if not _RUN_ID.fullmatch(run_id):
        return ()
    path = directory / "project_recommendations" / f"{run_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source") != "agent":
            return ()
        return tuple(dict.fromkeys(str(item["project_id"]) for item in data["recommendations"]))
    except FileNotFoundError:
        return ()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        logger.warning("Ignoring an unreadable project pick cache")
        return ()


def load_sources(family: str, university: str | None, gaps: list[dict], run_id: str,
                 directory: Path = LOCAL_RESULTS) -> Sources:
    """Read the catalogs, the shortlists and their picks for this run."""
    verified = [{"skill_id": gap["skill_id"], "skill_name": gap["skill_name"]} for gap in gaps]
    projects = project_shortlist(FAMILY_TO_CATALOG[family], None, verified)
    certifications = for_family(get_catalog(), family)

    project_ids = cached_project_picks(run_id, directory)
    if project_ids:
        project_picks = Picks(project_ids, "project_agent")
    else:
        ranked = rank_projects(FAMILY_TO_CATALOG[family], [], [gap["skill_name"] for gap in gaps],
                               verified_skill_gaps=verified)
        project_picks = Picks(tuple(item["project_id"] for item in ranked["recommendations"]), "rules")

    # The same skill-match picks the Resources page shows (there is no certification Agent).
    ranked = rank_certifications(certifications, family, gaps)
    certification_picks = Picks(tuple(item.certification_id for item in ranked), "rules")

    return Sources(resources=resources_for(family, university), projects=projects,
                   certifications=certifications, project_picks=project_picks,
                   certification_picks=certification_picks)


def build_candidates(gaps: list[dict], sources: Sources, *, taken_course_ids: set[str],
                     done_resource_ids: set[str]) -> Candidates:
    """Gap-closing candidates from each shortlist, ranked and capped per type.

    Removed: taken school courses and plan items already done. Saved-but-not-done items stay, so a
    suggested plan can include them (saving it then only sets their position).
    """
    gap_rank = {gap["skill_id"]: index for index, gap in enumerate(gaps)}
    cards = {resource["id"]: resource for resource in sources.resources}
    project_info = {project["id"]: project for project in sources.projects}
    certification_level = {item.id: item.level for item in sources.certifications}

    def candidate(resource_id: str, suggested_by: str) -> dict | None:
        card = cards.get(resource_id)
        if card is None or resource_id in done_resource_ids:
            return None
        if card["type"] == "school_course" and resource_id in taken_course_ids:
            return None
        skill_ids = sorted((skill for skill in card["skills"] if skill in gap_rank), key=gap_rank.__getitem__)
        if not skill_ids:
            return None
        project = project_info.get(resource_id)
        return {
            "resource_id": resource_id, "type": card["type"], "title": card["title"],
            "provider": card["provider"], "skill_ids": skill_ids,
            "difficulty": project["difficulty"] if project else certification_level.get(resource_id),
            "estimated_hours": project["estimated_hours"] if project else None,
            "alongside": bool(card.get("alongside")), "suggested_by": suggested_by,
        }

    def ranked(ids: list[str], picks: Picks | None, cap: int) -> list[dict]:
        chosen = set(picks.ids) if picks else set()
        items = [item for resource_id in dict.fromkeys(ids)
                 if (item := candidate(resource_id, picks.source if resource_id in chosen else "catalog"))]
        items.sort(key=lambda item: (item["suggested_by"] == "catalog", gap_rank[item["skill_ids"][0]],
                                     -len(item["skill_ids"]), _DIFFICULTY_ORDER.get(item["difficulty"], 1),
                                     item["resource_id"]))
        return items[:cap]

    items = [
        *ranked([project["id"] for project in sources.projects], sources.project_picks, PROJECT_CAP),
        *ranked([item.id for item in sources.certifications], sources.certification_picks, CERTIFICATION_CAP),
    ]
    for kind in CATALOG_TYPES:
        items += ranked([resource["id"] for resource in sources.resources if resource["type"] == kind], None, OTHER_CAP)
    return Candidates(items=items, resources={item["resource_id"]: cards[item["resource_id"]] for item in items})


def agent_payload(mode: str, family: str, gaps: list[dict], candidates: Candidates) -> dict:
    """INPUT_JSON for action-plan-agent: gaps by name in priority order, no scores or grades."""
    return {
        "mode": mode,
        "job_family": family,
        "gaps": [{"skill_id": gap["skill_id"], "skill_name": gap["skill_name"]} for gap in gaps],
        "candidates": candidates.items,
    }
