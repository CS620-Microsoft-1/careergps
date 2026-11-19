"""Manual live check of action-plan-agent with fake data; not part of CI (not named test_*).

Run from backend/ after `az login`:
    python -m tests.manual_action_plan_smoke [path/to/input.json]
Default input: docs/contracts/action-plan-input.example.json. Prints what the Agent chose, what the
validator dropped or filled, counts per type against the plan rules, and text-rule warnings.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import ActionPlanSettings  # noqa: E402
from app.services.action_plans import agent  # noqa: E402
from app.services.action_plans.candidates import Candidates  # noqa: E402
from app.services.action_plans.validation import (  # noqa: E402
    MAX_PER_TYPE, MIN_PER_TYPE, InvalidAgentAnswer, validate,
)

EXAMPLE = BACKEND_ROOT.parent / "docs" / "contracts" / "action-plan-input.example.json"
FILLED = "; added to complete your plan."
LIMITS = {"title": 6, "summary": 30, "reason": 25}


def words(text: str) -> int:
    return len(text.split())


def text_warnings(plan: dict, gaps: list[dict]) -> list[str]:
    """The Instructions' TEXT rules that the validator does not enforce."""
    skill_ids = {gap["skill_id"] for gap in gaps}
    warnings = []
    for field in ("title", "summary"):
        if words(plan[field]) > LIMITS[field]:
            warnings.append(f"{field} has {words(plan[field])} words (max {LIMITS[field]})")
    for item in plan["steps"] + plan["alongside"]:
        reason = item["reason"]
        if words(reason) > LIMITS["reason"]:
            warnings.append(f"{item['resource_id']}: reason has {words(reason)} words (max {LIMITS['reason']})")
        if re.search(r"\d", reason):
            warnings.append(f"{item['resource_id']}: reason contains a number")
        if "!" in reason:
            warnings.append(f"{item['resource_id']}: reason has an exclamation mark")
        if any(skill_id in reason for skill_id in skill_ids if "_" in skill_id):
            warnings.append(f"{item['resource_id']}: reason uses a skill_id instead of the skill_name")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, default=EXAMPLE)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    settings = ActionPlanSettings()
    if not agent.is_configured(settings):
        print("ACTION_PLAN_FOUNDRY_PROJECT_ENDPOINT is not set in backend/.env")
        return 1

    print(f"Agent: {settings.action_plan_foundry_agent_name} "
          f"(version {settings.pinned_agent_version or 'latest'}), input: {args.input.name}")
    started = time.monotonic()
    raw = agent.invoke(payload, settings=settings)
    print(f"Answered in {time.monotonic() - started:.1f} s\n")

    candidates = Candidates(items=payload["candidates"], resources={})
    by_id = {item["resource_id"]: item for item in candidates.items}
    raw_plan = (raw.get("plans") or [{}])[0]
    print("Raw answer:")
    print(json.dumps(raw, indent=2, ensure_ascii=False))

    try:
        [plan] = validate(raw, candidates, payload["gaps"], payload["mode"])
    except InvalidAgentAnswer as error:
        print(f"\nRejected by the validator: {error}. The app would show the rule plan.")
        return 1
    raw_ids = [item["resource_id"] for item in raw_plan.get("steps", []) + raw_plan.get("alongside", [])]
    final = plan.steps + plan.alongside
    final_ids = [item.resource_id for item in final]
    filled = [item.resource_id for item in final if item.reason.endswith(FILLED)]
    dropped = [resource_id for resource_id in raw_ids if resource_id not in final_ids]

    print(f"\nTitle:   {plan.title}\nSummary: {plan.summary}\n")
    for label, entries in (("Steps", plan.steps), ("Alongside", plan.alongside)):
        print(f"{label}:")
        for index, item in enumerate(entries, 1):
            kind = by_id[item.resource_id]["type"]
            mark = " [filled]" if item.resource_id in filled else ""
            print(f"  {index}. {item.resource_id} ({kind}) {item.skill_ids}{mark}\n     {item.reason}")

    counts = Counter(by_id[resource_id]["type"] for resource_id in final_ids)
    available = Counter(item["type"] for item in candidates.items)
    print("\nCounts (min-max):")
    for kind in MIN_PER_TYPE:
        needed = min(MIN_PER_TYPE[kind], available[kind])
        status = "ok" if needed <= counts[kind] <= MAX_PER_TYPE[kind] else "OUT OF RANGE"
        print(f"  {kind:14} {counts[kind]}  ({MIN_PER_TYPE[kind]}-{MAX_PER_TYPE[kind]}) {status}")

    covered = {skill for item in final for skill in item.skill_ids}
    uncovered = [gap["skill_id"] for gap in payload["gaps"] if gap["skill_id"] not in covered]
    warnings = text_warnings(raw_plan, payload["gaps"]) if raw_plan else []
    print(f"\nDropped by the validator: {dropped or 'none'}")
    print(f"Filled by the validator:  {filled or 'none'}  (fills mean the prompt missed a minimum)")
    print(f"Uncovered gaps:           {uncovered or 'none'}")
    print(f"Text warnings:            {warnings or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
