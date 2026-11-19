"""Suggest an action plan for a completed Skill Gap run: action-plan-agent first, the rule plan as fallback.

Flow: gaps → candidates (the specialists' shortlists) → Agent answer, validated → cards and Python-computed
totals. Only Agent plans are cached, under local_results/action_plans/{run_id}/{key}.json. The key hashes
everything the answer depends on (INPUT_JSON, the saved Instructions and response format, the Agent
version), so a taken course, new specialist picks or a prompt edit gets a fresh plan. Rule plans are free
and never cached, so a working Agent is never hidden behind an old fallback.
"""
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Callable

from pydantic import BaseModel

from app.core.config import BACKEND_ROOT, ActionPlanSettings
from app.schemas.action_plans import (
    ActionPlan, ActionPlanItem, ActionPlanMode, ActionPlanSuggestions, AgentPlan,
)
from app.schemas.resources import Resource
from app.schemas.skill_gap_web import SkillGapRun
from app.services.skill_gaps.storage import load, save_json
from . import agent, rules
from .candidates import (
    LOCAL_RESULTS, Candidates, Sources, agent_payload, build_candidates, gaps_from_report, load_sources,
)
from .validation import validate

logger = logging.getLogger(__name__)

PROMPT_DIR = BACKEND_ROOT / "app" / "prompts" / "action_plan"
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")

SourceLoader = Callable[[str, str | None, list[dict], str], Sources]


class _Cached(BaseModel):
    """Cache record: the validated Agent plans. Cards are attached on every read, so they stay current."""
    generated_at: str
    plans: list[AgentPlan]


class ActionPlanner:
    def __init__(self, directory: Path | None = None, *, settings: ActionPlanSettings | None = None,
                 invoker: Callable[[dict], dict] | None = None, configured: Callable[[], bool] | None = None,
                 sources: SourceLoader | None = None, prompt_dir: Path = PROMPT_DIR) -> None:
        self.directory = (directory or LOCAL_RESULTS / "action_plans").resolve()
        self._settings = settings
        self._invoke = invoker or (lambda payload: agent.invoke(payload, settings=self.settings))
        self._configured = configured or (lambda: agent.is_configured(self.settings))
        self._sources = sources or load_sources
        self._prompt_dir = prompt_dir
        self._locks: defaultdict[str, Lock] = defaultdict(Lock)
        self._locks_guard = Lock()

    @property
    def settings(self) -> ActionPlanSettings:
        # None: read backend/.env on every call, so a new Agent version needs no restart.
        return self._settings or ActionPlanSettings()

    def suggest(self, run: SkillGapRun, *, mode: ActionPlanMode = "full", university: str | None = None,
                taken_course_ids: set[str] = frozenset(), done_resource_ids: set[str] = frozenset(),
                ) -> ActionPlanSuggestions:
        if run.status != "completed" or run.report is None:
            raise ValueError("The skill gap analysis has not completed")
        if not _RUN_ID.fullmatch(run.id):
            raise ValueError("Unexpected run id")
        gaps = gaps_from_report(run.report)
        if not gaps:
            return self._response(run, mode, "rules", _now(), [], Candidates(items=[], resources={}), gaps)

        sources = self._sources(run.job_family, university, gaps, run.id)
        candidates = build_candidates(gaps, sources, taken_course_ids=set(taken_course_ids),
                                      done_resource_ids=set(done_resource_ids))
        payload = agent_payload(mode, run.job_family, gaps, candidates)
        path = self.directory / run.id / f"{self._cache_key(payload)}.json"

        with self._locks_guard:
            lock = self._locks[run.id]
        # One Agent call per run, even when the page asks twice at once.
        with lock:
            cached = self._read(path)
            if cached is not None:
                return self._response(run, mode, "agent", cached.generated_at, cached.plans, candidates, gaps)
            plans = self._agent_plans(payload, candidates, gaps, mode) if candidates.items else None
            if plans is not None:
                record = _Cached(generated_at=_now(), plans=plans)
                save_json(path, record.model_dump(mode="json"))
                return self._response(run, mode, "agent", record.generated_at, plans, candidates, gaps)

        plan = rules.full_plan(candidates, gaps)
        return self._response(run, mode, "rules", _now(), [plan] if plan else [], candidates, gaps)

    def _agent_plans(self, payload: dict, candidates: Candidates, gaps: list[dict],
                     mode: str) -> list[AgentPlan] | None:
        if not self._configured():
            return None
        try:
            return validate(self._invoke(payload), candidates, gaps, mode)
        except Exception as error:
            # Error type only: SDK messages can echo the payload. The student still gets the rule plan.
            logger.warning("Action plan Agent failed (%s); using the rule plan", type(error).__name__)
            return None

    def _cache_key(self, payload: dict) -> str:
        digest = hashlib.sha256()
        digest.update(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        for name in ("Instructions.md", "response-format.json"):
            digest.update(b"\0" + (self._prompt_dir / name).read_bytes())
        settings = self.settings
        digest.update(f"\0{settings.action_plan_foundry_agent_name}\0{settings.pinned_agent_version}".encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _read(path: Path) -> _Cached | None:
        try:
            return _Cached.model_validate(load(path))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.warning("Ignoring an unreadable action plan cache")
            return None

    @staticmethod
    def _response(run: SkillGapRun, mode: str, source: str, generated_at: str, plans: list[AgentPlan],
                  candidates: Candidates, gaps: list[dict]) -> ActionPlanSuggestions:
        enriched = [enrich(plan, candidates, gaps) for plan in plans]
        covered = {skill for plan in enriched for skill in plan.covered_skill_ids}
        return ActionPlanSuggestions(
            job_family=run.job_family, skill_gap_run_id=run.id, mode=mode, source=source,
            generated_at=generated_at, plans=enriched,
            uncovered_skill_ids=[gap["skill_id"] for gap in gaps if gap["skill_id"] not in covered])


def enrich(plan: AgentPlan, candidates: Candidates, gaps: list[dict]) -> ActionPlan:
    """Attach resource cards and compute the totals in Python (never by the Agent)."""
    by_id = {item["resource_id"]: item for item in candidates.items}

    def items(entries) -> list[ActionPlanItem]:
        return [ActionPlanItem(resource_id=entry.resource_id, skill_ids=entry.skill_ids, reason=entry.reason,
                               resource=Resource.model_validate(candidates.resources[entry.resource_id]))
                for entry in entries
                if entry.resource_id in candidates.resources and entry.skill_ids]

    steps, alongside = items(plan.steps), items(plan.alongside)
    claimed = {skill for entry in steps + alongside for skill in entry.skill_ids}
    hours = [by_id[entry.resource_id]["estimated_hours"] for entry in steps
             if by_id.get(entry.resource_id, {}).get("type") == "project"
             and by_id[entry.resource_id]["estimated_hours"] is not None]
    return ActionPlan(strategy=plan.strategy, title=plan.title, summary=plan.summary, steps=steps,
                      alongside=alongside,
                      covered_skill_ids=[gap["skill_id"] for gap in gaps if gap["skill_id"] in claimed],
                      project_hours=sum(hours) if hours else None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_manager_lock = Lock()


@lru_cache(maxsize=1)
def _cached_planner() -> ActionPlanner:
    return ActionPlanner()


def get_action_planner() -> ActionPlanner:
    with _manager_lock:
        return _cached_planner()
