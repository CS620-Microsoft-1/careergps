"""Action plan suggestions from the action plan Agent (app/prompts/action_plan/) or the rule planner.

Three layers: the request from the frontend, the Agent's raw answer (mirrors
app/prompts/action_plan/response-format.json; untrusted until validated), and the API response,
whose items are validated and carry the full resource card.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resources import Resource
from app.schemas.skill_gap_web import JobFamily

# PR 2 adds "skill", PR 3 "extend".
ActionPlanMode = Literal["full"]
ActionPlanStrategy = Literal["balanced", "fastest", "hands_on", "credential", "campus"]
ActionPlanSource = Literal["agent", "rules"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Request (frontend → API) ────────────────────────────────────────────────────────────────────


class ActionPlanRequest(_Strict):
    job_family: JobFamily
    mode: ActionPlanMode = "full"


# ── Agent output (must match response-format.json) ──────────────────────────────────────────────


class AgentPlanItem(_Strict):
    resource_id: str
    skill_ids: list[str]
    reason: str


class AgentPlan(_Strict):
    strategy: ActionPlanStrategy
    title: str
    summary: str
    steps: list[AgentPlanItem]
    alongside: list[AgentPlanItem]


class AgentOutput(_Strict):
    plans: list[AgentPlan]


# ── API response (API → frontend) ───────────────────────────────────────────────────────────────


class ActionPlanItem(BaseModel):
    resource_id: str
    # Gap skills this resource really closes (checked against the catalog and the run's gaps).
    skill_ids: list[str] = Field(min_length=1)
    # The mentor's sentence from the Agent; "" when there is none (rule plan, filled-in step, blank answer).
    reason: str
    resource: Resource


class ActionPlan(BaseModel):
    strategy: ActionPlanStrategy
    title: str
    summary: str
    # Main path in order: steps[0] is what the student starts now.
    steps: list[ActionPlanItem]
    # Ongoing commitments (clubs, meetups) that run next to the main path.
    alongside: list[ActionPlanItem]
    # Computed in Python, never by the Agent.
    covered_skill_ids: list[str]
    # Sum of the projects' estimated_hours; None when the plan has no project.
    project_hours: int | None


class ActionPlanSuggestions(BaseModel):
    job_family: JobFamily
    skill_gap_run_id: str
    mode: ActionPlanMode
    source: ActionPlanSource
    generated_at: str
    plans: list[ActionPlan]
    # Top gaps that no item in any plan closes; computed in Python.
    uncovered_skill_ids: list[str]
