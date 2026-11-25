"""Check and clean action-plan-agent's answer before a student sees it.

Every item must be a candidate and claim only gap skills that candidate closes. Placement follows the
candidate (clubs alongside), per-type maximums drop extras, and a missed minimum is filled with the
best-ranked unused candidate of that type, placed by gap and learn → prove → certify. An answer that is malformed or has no usable main path raises
InvalidAgentAnswer, and the planner uses the rule plan instead.
"""
from pydantic import ValidationError

from app.schemas.action_plans import AgentOutput, AgentPlan, AgentPlanItem
from app.services.action_plans.candidates import Candidates

# The plan's parts (app/prompts/action_plan/Instructions.md, PICK).
MAX_PER_TYPE = {"project": 3, "school_course": 2, "online_course": 2, "certification": 2, "student_org": 2}
MIN_PER_TYPE = {"project": 2, "school_course": 1, "online_course": 1, "certification": 1, "student_org": 1}
# Within one gap: learn, then prove, then certify.
STEP_ORDER = {"online_course": 0, "school_course": 1, "project": 2, "certification": 3, "student_org": 4}
DEFAULT_TITLE = "Your action plan"
DEFAULT_SUMMARY = "You close your highest-priority gaps first, in this order."


class InvalidAgentAnswer(ValueError):
    """The answer can't be used; the planner falls back to the rule plan."""


def skill_names(skill_ids: list[str], gaps: list[dict]) -> str:
    names = {gap["skill_id"]: gap["skill_name"] for gap in gaps}
    return ", ".join(names.get(skill, skill) for skill in skill_ids)


def plain_reason(skill_ids: list[str], gaps: list[dict], *, added: bool = False) -> str:
    """Text for an item without a mentor sentence (blank reasons, filled minimums, the rule plan)."""
    return f"Closes {skill_names(skill_ids, gaps)}" + ("; added to complete your plan." if added else ".")


def validate(raw: object, candidates: Candidates, gaps: list[dict], mode: str = "full") -> list[AgentPlan]:
    """The Agent's plans, cleaned; raises InvalidAgentAnswer when nothing usable is left."""
    try:
        output = AgentOutput.model_validate(raw)
    except ValidationError as error:
        raise InvalidAgentAnswer("The answer does not match the response format") from error
    if mode != "full":
        raise InvalidAgentAnswer(f"Mode {mode!r} is not enabled")
    if not output.plans:
        raise InvalidAgentAnswer("The answer has no plan")
    plan = clean_plan(output.plans[0], candidates, gaps)
    return [plan.model_copy(update={"strategy": "balanced"})]


def clean_plan(plan: AgentPlan, candidates: Candidates, gaps: list[dict]) -> AgentPlan:
    by_id = {item["resource_id"]: item for item in candidates.items}
    used: set[str] = set()
    counts = dict.fromkeys(MAX_PER_TYPE, 0)
    steps: list[AgentPlanItem] = []
    alongside: list[AgentPlanItem] = []

    # Agent order: main path first, then alongside; placement then follows the candidate.
    for item in [*plan.steps, *plan.alongside]:
        candidate = by_id.get(item.resource_id)
        if candidate is None or item.resource_id in used:
            continue
        claimed = set(item.skill_ids)
        skill_ids = [skill for skill in candidate["skill_ids"] if skill in claimed]
        if not skill_ids or counts[candidate["type"]] >= MAX_PER_TYPE[candidate["type"]]:
            continue
        reason = item.reason.strip() or plain_reason(skill_ids, gaps)
        (alongside if candidate["alongside"] else steps).append(
            AgentPlanItem(resource_id=item.resource_id, skill_ids=skill_ids, reason=reason))
        used.add(item.resource_id)
        counts[candidate["type"]] += 1

    if not steps:
        raise InvalidAgentAnswer("No usable main-path step")

    gap_rank = {gap["skill_id"]: index for index, gap in enumerate(gaps)}

    def place(item: AgentPlanItem) -> tuple[int, int]:
        """Biggest gap the item closes, then learn → prove → certify."""
        return (min((gap_rank.get(skill, len(gaps)) for skill in item.skill_ids), default=len(gaps)),
                STEP_ORDER[by_id[item.resource_id]["type"]])

    # Fill a missed minimum with the best-ranked unused candidate of that type (candidates are ranked).
    # The Agent's own steps keep their order; a filler goes before the first step that should come after it.
    for kind, minimum in MIN_PER_TYPE.items():
        for candidate in candidates.items:
            if counts[kind] >= minimum:
                break
            if candidate["type"] != kind or candidate["resource_id"] in used:
                continue
            filler = AgentPlanItem(resource_id=candidate["resource_id"], skill_ids=candidate["skill_ids"],
                                   reason=plain_reason(candidate["skill_ids"], gaps, added=True))
            target = alongside if candidate["alongside"] else steps
            at = next((index for index, step in enumerate(target) if place(step) > place(filler)), len(target))
            target.insert(at, filler)
            used.add(candidate["resource_id"])
            counts[kind] += 1

    return AgentPlan(strategy=plan.strategy, title=plan.title.strip() or DEFAULT_TITLE,
                     summary=plan.summary.strip() or DEFAULT_SUMMARY, steps=steps, alongside=alongside)
