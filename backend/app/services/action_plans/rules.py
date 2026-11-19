"""The free fallback when action-plan-agent is unavailable or its answer is rejected.

Same composition rules as the Agent (validation.MIN_PER_TYPE / MAX_PER_TYPE) and the same output shape
as a validated Agent plan, so the planner treats both alike. Deterministic: no model call, no randomness.
"""
from app.schemas.action_plans import AgentPlan, AgentPlanItem
from app.services.action_plans.candidates import Candidates
from app.services.action_plans.validation import (
    DEFAULT_SUMMARY, DEFAULT_TITLE, MAX_PER_TYPE, MIN_PER_TYPE, plain_reason,
)

# Within one gap: learn, then prove, then certify.
_STEP_ORDER = {"online_course": 0, "school_course": 1, "project": 2, "certification": 3, "student_org": 4}


def full_plan(candidates: Candidates, gaps: list[dict]) -> AgentPlan | None:
    """One balanced plan, or None when no candidate can go on the main path."""
    gap_rank = {gap["skill_id"]: index for index, gap in enumerate(gaps)}
    candidate_rank = {item["resource_id"]: index for index, item in enumerate(candidates.items)}
    chosen: list[dict] = []
    covered: set[str] = set()
    counts = dict.fromkeys(MAX_PER_TYPE, 0)

    def take(item: dict) -> None:
        chosen.append(item)
        covered.update(item["skill_ids"])
        counts[item["type"]] += 1

    def unused(item: dict) -> bool:
        return item not in chosen and counts[item["type"]] < MAX_PER_TYPE[item["type"]]

    def first_new_gap(item: dict) -> int:
        """Rank of the highest-priority gap this item closes that nothing chosen covers yet."""
        return min((gap_rank[skill] for skill in item["skill_ids"] if skill not in covered), default=len(gaps))

    # 1. Each type's minimum: the candidate that reaches the most urgent uncovered gap.
    for kind, minimum in MIN_PER_TYPE.items():
        while counts[kind] < minimum:
            pool = [item for item in candidates.items if item["type"] == kind and unused(item)]
            if not pool:
                break
            take(min(pool, key=lambda item: (first_new_gap(item), candidate_rank[item["resource_id"]])))

    # 2. Then cover the remaining gaps in priority order, within the maximums. No padding.
    for gap in gaps:
        if gap["skill_id"] in covered:
            continue
        pool = [item for item in candidates.items if gap["skill_id"] in item["skill_ids"] and unused(item)]
        if pool:
            take(min(pool, key=lambda item: candidate_rank[item["resource_id"]]))

    def order(item: dict) -> tuple:
        return (min(gap_rank[skill] for skill in item["skill_ids"]), _STEP_ORDER[item["type"]],
                candidate_rank[item["resource_id"]])

    def plan_item(item: dict) -> AgentPlanItem:
        return AgentPlanItem(resource_id=item["resource_id"], skill_ids=item["skill_ids"],
                             reason=plain_reason(item["skill_ids"], gaps))

    steps = [plan_item(item) for item in sorted(chosen, key=order) if not item["alongside"]]
    if not steps:
        return None
    alongside = [plan_item(item) for item in sorted(chosen, key=order) if item["alongside"]]
    return AgentPlan(strategy="balanced", title=DEFAULT_TITLE, summary=DEFAULT_SUMMARY,
                     steps=steps, alongside=alongside)
