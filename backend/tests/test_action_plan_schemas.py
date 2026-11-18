import json
import unittest
from typing import get_args

from pydantic import ValidationError

from app.core.config import BACKEND_ROOT
from app.schemas.action_plans import (
    ActionPlanRequest, ActionPlanStrategy, AgentOutput, AgentPlan, AgentPlanItem,
)
from app.schemas.resources import PlanItem, PlanItemUpdate

RESPONSE_FORMAT = BACKEND_ROOT / "app" / "prompts" / "action_plan" / "response-format.json"


def agent_answer(**plan_overrides) -> dict:
    item = {"resource_id": "swe_01", "skill_ids": ["testing"], "reason": "Prove testing on real code first."}
    plan = {"strategy": "balanced", "title": "Close testing first", "summary": "You fix testing first.",
            "steps": [item], "alongside": [], **plan_overrides}
    return {"plans": [plan]}


class ContractSyncTest(unittest.TestCase):
    """The Pydantic models must match the response format pasted into Foundry."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(RESPONSE_FORMAT.read_text(encoding="utf-8"))["schema"]

    def test_output_fields_match(self) -> None:
        self.assertEqual(set(self.schema["properties"]), set(AgentOutput.model_fields))

    def test_plan_fields_and_strategies_match(self) -> None:
        plan = self.schema["properties"]["plans"]["items"]
        self.assertEqual(set(plan["properties"]), set(AgentPlan.model_fields))
        self.assertEqual(plan["properties"]["strategy"]["enum"], list(get_args(ActionPlanStrategy)))

    def test_item_fields_match(self) -> None:
        self.assertEqual(set(self.schema["$defs"]["item"]["properties"]), set(AgentPlanItem.model_fields))


class AgentOutputTest(unittest.TestCase):
    def test_parses_a_valid_answer(self) -> None:
        output = AgentOutput.model_validate(agent_answer())
        self.assertEqual(output.plans[0].steps[0].resource_id, "swe_01")

    def test_rejects_invalid_answers(self) -> None:
        missing_alongside = agent_answer()
        del missing_alongside["plans"][0]["alongside"]
        extra_field = agent_answer()
        extra_field["plans"][0]["steps"][0]["hours"] = 20
        for name, answer in {"unknown strategy": agent_answer(strategy="random"),
                             "missing alongside": missing_alongside,
                             "extra item field": extra_field}.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                AgentOutput.model_validate(answer)


class ActionPlanRequestTest(unittest.TestCase):
    def test_defaults_to_full_mode(self) -> None:
        self.assertEqual(ActionPlanRequest(job_family="software_engineer").mode, "full")

    def test_rejects_unknown_fields_modes_and_families(self) -> None:
        for name, data in {"extra field": {"job_family": "software_engineer", "skill_id": "testing"},
                           "mode not enabled yet": {"job_family": "software_engineer", "mode": "skill"},
                           "unknown family": {"job_family": "astronaut"}}.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                ActionPlanRequest.model_validate(data)


class PlanPositionSchemaTest(unittest.TestCase):
    def test_update_accepts_a_positive_position_or_none(self) -> None:
        self.assertIsNone(PlanItemUpdate(job_family="data_analyst").position)
        self.assertEqual(PlanItemUpdate(job_family="data_analyst", position=1).position, 1)
        for bad in (0, -2):
            with self.subTest(position=bad), self.assertRaises(ValidationError):
                PlanItemUpdate(job_family="data_analyst", position=bad)

    def test_item_position_is_optional(self) -> None:
        self.assertIsNone(PlanItem(resource_id="x", status="saved", saved_at="2026-01-01T00:00:00+00:00").position)


if __name__ == "__main__":
    unittest.main()
