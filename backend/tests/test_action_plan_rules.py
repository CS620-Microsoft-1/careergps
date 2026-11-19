import unittest
from collections import Counter

from app.services.action_plans.candidates import Candidates
from app.services.action_plans.rules import full_plan
from app.services.action_plans.validation import MAX_PER_TYPE, validate

GAPS = [{"skill_id": "system_design", "skill_name": "System design"},
        {"skill_id": "testing", "skill_name": "Testing"},
        {"skill_id": "cloud", "skill_name": "Cloud"},
        {"skill_id": "security", "skill_name": "Security"}]


def candidate(resource_id: str, kind: str, skills: list[str], alongside: bool = False) -> dict:
    return {"resource_id": resource_id, "type": kind, "title": resource_id, "provider": "", "skill_ids": skills,
            "difficulty": None, "estimated_hours": None, "alongside": alongside, "suggested_by": "catalog"}


ITEMS = [  # ranked within each type, as build_candidates returns them
    candidate("p_test", "project", ["testing"]),
    candidate("p_design", "project", ["system_design"]),
    candidate("p_cloud", "project", ["cloud"]),
    candidate("p_test2", "project", ["testing"]),
    candidate("cert_design", "certification", ["system_design"]),
    candidate("cert_sec", "certification", ["security"]),
    candidate("cs_design", "school_course", ["system_design"]),
    candidate("cs_test", "school_course", ["testing"]),
    candidate("online_test", "online_course", ["testing"]),
    candidate("online_design", "online_course", ["system_design"]),
    candidate("club_cloud", "student_org", ["cloud"], alongside=True),
]


def plan_for(items=ITEMS):
    return full_plan(Candidates(items=list(items), resources={}), GAPS)


def ids(plan_items) -> list[str]:
    return [item.resource_id for item in plan_items]


def kinds(plan) -> Counter:
    by_id = {item["resource_id"]: item["type"] for item in ITEMS}
    return Counter(by_id[i] for i in ids(plan.steps) + ids(plan.alongside))


class FullPlanTest(unittest.TestCase):
    def test_meets_every_minimum(self) -> None:
        counts = kinds(plan_for())
        self.assertGreaterEqual(counts["project"], 2)
        for kind in ("school_course", "online_course", "certification", "student_org"):
            self.assertGreaterEqual(counts[kind], 1, kind)

    def test_respects_maximums_and_does_not_pad(self) -> None:
        counts = kinds(plan_for())
        for kind, maximum in MAX_PER_TYPE.items():
            self.assertLessEqual(counts[kind], maximum, kind)
        # Every gap is covered after the minimums plus cert_sec, so nothing else is added.
        self.assertNotIn("p_test2", ids(plan_for().steps))
        self.assertEqual(counts["school_course"], 1)

    def test_minimum_picks_reach_uncovered_gaps(self) -> None:
        plan = plan_for()
        self.assertIn("cert_sec", ids(plan.steps))  # beats cert_design: security isn't covered yet
        covered = {skill for item in plan.steps + plan.alongside for skill in item.skill_ids}
        self.assertEqual(covered, {"system_design", "testing", "cloud", "security"})

    def test_adds_an_extra_item_for_a_gap_still_uncovered(self) -> None:
        items = [item for item in ITEMS if item["resource_id"] != "cert_sec"]
        items.append(candidate("p_sec", "project", ["security"]))
        plan = plan_for(items)
        self.assertIn("p_sec", ids(plan.steps))  # third project, within the maximum of 3

    def test_orders_by_gap_then_learn_prove_certify(self) -> None:
        self.assertEqual(ids(plan_for().steps), ["cs_design", "p_design", "online_test", "p_test", "cert_sec"])

    def test_clubs_go_alongside(self) -> None:
        plan = plan_for()
        self.assertEqual(ids(plan.alongside), ["club_cloud"])
        self.assertNotIn("club_cloud", ids(plan.steps))

    def test_skips_types_without_candidates(self) -> None:
        plan = plan_for([item for item in ITEMS if item["type"] == "project"])
        self.assertEqual(set(kinds(plan)), {"project"})
        self.assertEqual(plan.alongside, [])

    def test_is_deterministic_and_plain(self) -> None:
        self.assertEqual(plan_for(), plan_for())
        plan = plan_for()
        self.assertEqual(plan.strategy, "balanced")
        self.assertEqual(plan.steps[0].reason, "Closes System design.")

    def test_none_without_main_path_candidates(self) -> None:
        self.assertIsNone(plan_for([item for item in ITEMS if item["alongside"]]))
        self.assertIsNone(plan_for([]))

    def test_passes_the_agent_validation_rules_unchanged(self) -> None:
        candidates = Candidates(items=ITEMS, resources={})
        plan = full_plan(candidates, GAPS)
        [validated] = validate({"plans": [plan.model_dump()]}, candidates, GAPS)
        self.assertEqual(validated, plan)


if __name__ == "__main__":
    unittest.main()
