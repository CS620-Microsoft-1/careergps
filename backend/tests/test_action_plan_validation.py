import unittest

from app.services.action_plans.candidates import Candidates
from app.services.action_plans.validation import (
    DEFAULT_SUMMARY, DEFAULT_TITLE, InvalidAgentAnswer, validate,
)

GAPS = [{"skill_id": "system_design", "skill_name": "System design"},
        {"skill_id": "testing", "skill_name": "Testing"},
        {"skill_id": "cloud", "skill_name": "Cloud"}]


def candidate(resource_id: str, kind: str, skills: list[str], alongside: bool = False) -> dict:
    return {"resource_id": resource_id, "type": kind, "title": resource_id, "provider": "", "skill_ids": skills,
            "difficulty": None, "estimated_hours": None, "alongside": alongside, "suggested_by": "catalog"}


# Already ranked within each type, as build_candidates returns them.
CANDIDATES = Candidates(items=[
    candidate("p1", "project", ["system_design", "testing"]),
    candidate("p2", "project", ["testing"]),
    candidate("p3", "project", ["cloud"]),
    candidate("p4", "project", ["testing"]),
    candidate("cert1", "certification", ["cloud"]),
    candidate("cert2", "certification", ["system_design"]),
    candidate("cert3", "certification", ["testing"]),
    candidate("cs400", "school_course", ["system_design"]),
    candidate("sql", "online_course", ["testing"]),
    candidate("club", "student_org", ["cloud"], alongside=True),
], resources={})


def item(resource_id: str, skills: list[str], reason: str = "Do this because it proves the skill.") -> dict:
    return {"resource_id": resource_id, "skill_ids": skills, "reason": reason}


def answer(steps: list[dict], alongside: list[dict] | None = None, **plan) -> dict:
    return {"plans": [{"strategy": "balanced", "title": "Fix design first", "summary": "You start with design.",
                       "steps": steps, "alongside": alongside or [], **plan}]}


COMPLETE = answer(
    [item("cs400", ["system_design"]), item("p1", ["system_design", "testing"]), item("sql", ["testing"]),
     item("p2", ["testing"]), item("cert1", ["cloud"])],
    [item("club", ["cloud"])])


def ids(plan_items) -> list[str]:
    return [entry.resource_id for entry in plan_items]


def step(plan, resource_id: str):
    return next(entry for entry in plan.steps if entry.resource_id == resource_id)


class ValidAnswerTest(unittest.TestCase):
    def test_complete_answer_passes_unchanged(self) -> None:
        [plan] = validate(COMPLETE, CANDIDATES, GAPS)
        self.assertEqual(ids(plan.steps), ["cs400", "p1", "sql", "p2", "cert1"])
        self.assertEqual(ids(plan.alongside), ["club"])
        self.assertEqual(plan.steps[0].reason, "Do this because it proves the skill.")
        self.assertEqual((plan.title, plan.summary), ("Fix design first", "You start with design."))


class RejectTest(unittest.TestCase):
    def test_malformed_answers_are_rejected(self) -> None:
        for name, raw in {"not an object": "plans", "unknown strategy": answer([], strategy="random"),
                          "extra field": {"plans": [], "note": "x"}, "no plan": {"plans": []}}.items():
            with self.subTest(name), self.assertRaises(InvalidAgentAnswer):
                validate(raw, CANDIDATES, GAPS)

    def test_no_usable_main_path_is_rejected(self) -> None:
        raw = answer([item("made_up", ["testing"]), item("p3", ["testing"])], [item("club", ["cloud"])])
        with self.assertRaises(InvalidAgentAnswer):
            validate(raw, CANDIDATES, GAPS)

    def test_modes_other_than_full_are_rejected(self) -> None:
        with self.assertRaises(InvalidAgentAnswer):
            validate(COMPLETE, CANDIDATES, GAPS, mode="skill")


class CleaningTest(unittest.TestCase):
    def test_keeps_only_the_first_plan_as_balanced(self) -> None:
        raw = {"plans": [answer(COMPLETE["plans"][0]["steps"], strategy="hands_on")["plans"][0],
                         answer([item("p3", ["cloud"])])["plans"][0]]}
        plans = validate(raw, CANDIDATES, GAPS)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].strategy, "balanced")
        self.assertIn("cs400", ids(plans[0].steps))

    def test_drops_unknown_and_duplicate_resources(self) -> None:
        raw = answer([item("p1", ["testing"]), item("invented", ["testing"]), item("p1", ["testing"]),
                      item("p2", ["testing"])])
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertNotIn("invented", ids(plan.steps))
        self.assertEqual(ids(plan.steps).count("p1"), 1)

    def test_keeps_only_skills_the_candidate_closes_in_gap_order(self) -> None:
        raw = answer([item("p1", ["testing", "cloud", "system_design"]), item("p2", ["cloud"]), item("p4", ["testing"])])
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertEqual(step(plan, "p1").skill_ids, ["system_design", "testing"])
        self.assertNotIn("p2", ids(plan.steps))  # p2 claimed only a skill it doesn't close

    def test_placement_follows_the_candidate(self) -> None:
        raw = answer([item("p1", ["testing"]), item("club", ["cloud"])], [item("p2", ["testing"])])
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertEqual(ids(plan.alongside), ["club"])
        self.assertEqual([i for i in ids(plan.steps) if i in {"p1", "p2"}], ["p1", "p2"])

    def test_drops_items_over_the_maximum(self) -> None:
        raw = answer([item(p, ["testing"] if p != "p3" else ["cloud"]) for p in ("p1", "p2", "p3", "p4")]
                     + [item("cert1", ["cloud"]), item("cert2", ["system_design"]), item("cert3", ["testing"])])
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertEqual([i for i in ids(plan.steps) if i.startswith("p")], ["p1", "p2", "p3"])
        self.assertEqual([i for i in ids(plan.steps) if i.startswith("cert")], ["cert1", "cert2"])

    def test_blank_text_gets_plain_defaults(self) -> None:
        raw = answer([item("p1", ["system_design"], reason="  ")], title=" ", summary="")
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertEqual((plan.title, plan.summary), (DEFAULT_TITLE, DEFAULT_SUMMARY))
        # No "Closes …" stand-in: the card already lists the skills (review on PR #58).
        self.assertEqual(step(plan, "p1").reason, "")


class FillMinimumsTest(unittest.TestCase):
    def test_fills_each_missing_type_with_its_best_ranked_candidate(self) -> None:
        [plan] = validate(answer([item("p3", ["cloud"])]), CANDIDATES, GAPS)
        # Each filler goes in by its biggest gap, then learn → prove → certify.
        self.assertEqual(ids(plan.steps), ["cs400", "p1", "sql", "p3", "cert1"])
        self.assertEqual(ids(plan.alongside), ["club"])
        self.assertEqual(plan.steps[3].reason, "Do this because it proves the skill.")
        self.assertEqual(plan.steps[1].reason, "")

    def test_a_missed_online_course_goes_before_the_certification(self) -> None:
        # Review on PR #58: a filler must not land after the certification ("certify, then learn").
        raw = answer([item("cs400", ["system_design"]), item("p1", ["system_design", "testing"]),
                      item("p2", ["testing"]), item("cert1", ["cloud"])], [item("club", ["cloud"])])
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertEqual(ids(plan.steps), ["cs400", "p1", "sql", "p2", "cert1"])

    def test_fillers_keep_the_agents_own_order(self) -> None:
        # The Agent put the certification first; a filler doesn't reorder the Agent's steps.
        raw = answer([item("cert2", ["system_design"]), item("p1", ["testing"]), item("p2", ["testing"]),
                      item("cs400", ["system_design"]), item("sql", ["testing"])], [item("club", ["cloud"])])
        [plan] = validate(raw, CANDIDATES, GAPS)
        self.assertEqual(ids(plan.steps), ["cert2", "p1", "p2", "cs400", "sql"])

    def test_skips_types_without_candidates(self) -> None:
        only_projects = Candidates(items=[c for c in CANDIDATES.items if c["type"] == "project"], resources={})
        [plan] = validate(answer([item("p1", ["testing"]), item("p2", ["testing"])]), only_projects, GAPS)
        self.assertEqual(ids(plan.steps), ["p1", "p2"])
        self.assertEqual(plan.alongside, [])


if __name__ == "__main__":
    unittest.main()
