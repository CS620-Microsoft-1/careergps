import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from app.core.config import ActionPlanSettings
from app.schemas.skill_gap_web import SkillGapRun
from app.services.action_plans.candidates import Picks, Sources
from app.services.action_plans.planner import ActionPlanner

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = "b" * 32
PRIORITIES = {"system_design": 0.9, "testing": 0.7, "cloud": 0.5, "security": 0.3}


def run(status="completed", priorities=PRIORITIES) -> SkillGapRun:
    report = {"skills": [{"skill_id": skill, "skill_name": skill.replace("_", " ").title(), "skill_gap": 1.0,
                          "skill_gap_grade": "F", "priority": value, "resume_evidence_strength": 0.0}
                         for skill, value in priorities.items()]}
    return SkillGapRun(id=RUN_ID, user_id=USER_ID, resume_id=USER_ID, status=status, phase=status,
                       job_family="software_engineer", filename="r.pdf", resume_hash="h",
                       created_at="2026-11-19T00:00:00+00:00", completed_at="2026-11-19T00:00:01+00:00",
                       elapsed_seconds=1.0, model_calls=1, report=report if status == "completed" else None,
                       error=None)


def card(resource_id: str, kind: str, skills: list[str], alongside: bool = False) -> dict:
    return {"id": resource_id, "type": kind, "title": resource_id.title(), "provider": "Fake", "meta": "",
            "description": "Fake resource.", "skills": skills, "alongside": alongside}


CARDS = [
    card("p_design", "project", ["system_design"]),
    card("p_test", "project", ["testing"]),
    card("p_cloud", "project", ["cloud"]),
    card("cert_sec", "certification", ["security"]),
    card("cs_design", "school_course", ["system_design"]),
    card("online_test", "online_course", ["testing"]),
    card("club_cloud", "student_org", ["cloud"], alongside=True),
]
PROJECTS = [{"id": "p_design", "difficulty": "intermediate", "estimated_hours": 30},
            {"id": "p_test", "difficulty": "beginner", "estimated_hours": 12},
            {"id": "p_cloud", "difficulty": "beginner", "estimated_hours": None}]


def fake_sources(*_args) -> Sources:
    return Sources(resources=CARDS, projects=PROJECTS, certifications=[SimpleNamespace(id="cert_sec", level=None)],
                   project_picks=Picks((), "rules"), certification_picks=Picks((), "rules"))


def step(resource_id: str, skills: list[str]) -> dict:
    return {"resource_id": resource_id, "skill_ids": skills, "reason": "Build it, then show it."}


AGENT_ANSWER = {"plans": [{
    "strategy": "balanced", "title": "Design first", "summary": "You fix design, then testing.",
    "steps": [step("cs_design", ["system_design"]), step("p_design", ["system_design"]),
              step("online_test", ["testing"]), step("p_test", ["testing"]), step("cert_sec", ["security"])],
    "alongside": [step("club_cloud", ["cloud"])],
}]}


class FakeAgent:
    def __init__(self, answer=AGENT_ANSWER, error: Exception | None = None, delay: float = 0.0):
        self.answer, self.error, self.delay = answer, error, delay
        self.payloads: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer


class PlannerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prompts = Path(self.temp.name) / "prompts"
        self.prompts.mkdir()
        (self.prompts / "Instructions.md").write_text("Be strict.", encoding="utf-8")
        (self.prompts / "response-format.json").write_text("{}", encoding="utf-8")

    def planner(self, agent: FakeAgent | None = None, configured: bool = True, version: str = "latest",
                sources=fake_sources) -> ActionPlanner:
        settings = ActionPlanSettings(_env_file=None, action_plan_foundry_project_endpoint="https://example.test",
                                      action_plan_foundry_agent_version=version)
        return ActionPlanner(Path(self.temp.name) / "cache", settings=settings, invoker=agent or FakeAgent(),
                             configured=lambda: configured, sources=sources, prompt_dir=self.prompts)

    def cache_files(self) -> list[Path]:
        return list((Path(self.temp.name) / "cache").glob("*/*.json"))


class AgentPathTest(PlannerTestCase):
    def test_agent_plan_is_returned_and_cached(self) -> None:
        agent = FakeAgent()
        planner = self.planner(agent)
        first = planner.suggest(run())
        second = planner.suggest(run())
        self.assertEqual(first.source, "agent")
        self.assertEqual([item.resource_id for item in first.plans[0].steps],
                         ["cs_design", "p_design", "online_test", "p_test", "cert_sec"])
        self.assertEqual(len(agent.payloads), 1)
        self.assertEqual(second, first)
        self.assertEqual(len(self.cache_files()), 1)
        self.assertEqual(self.cache_files()[0].parent.name, RUN_ID)

    def test_payload_sends_gap_names_in_priority_order_only(self) -> None:
        agent = FakeAgent()
        self.planner(agent).suggest(run())
        gaps = agent.payloads[0]["gaps"]
        self.assertEqual([gap["skill_id"] for gap in gaps], ["system_design", "testing", "cloud", "security"])
        self.assertEqual(set(gaps[0]), {"skill_id", "skill_name"})

    def test_a_changed_candidate_list_calls_the_agent_again(self) -> None:
        agent = FakeAgent()
        planner = self.planner(agent)
        planner.suggest(run())
        result = planner.suggest(run(), done_resource_ids={"p_cloud"})
        self.assertEqual(len(agent.payloads), 2)
        self.assertEqual(result.source, "agent")

    def test_a_prompt_edit_or_new_version_calls_the_agent_again(self) -> None:
        agent = FakeAgent()
        self.planner(agent).suggest(run())
        (self.prompts / "Instructions.md").write_text("Be stricter.", encoding="utf-8")
        self.planner(agent).suggest(run())
        self.planner(agent, version="3").suggest(run())
        self.assertEqual(len(agent.payloads), 3)

    def test_two_calls_at_once_make_one_agent_call(self) -> None:
        agent = FakeAgent(delay=0.2)
        planner = self.planner(agent)
        results = []
        threads = [threading.Thread(target=lambda: results.append(planner.suggest(run()))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(agent.payloads), 1)
        self.assertEqual([result.source for result in results], ["agent", "agent"])


class FallbackTest(PlannerTestCase):
    def test_agent_error_uses_rules_and_is_not_cached(self) -> None:
        with self.assertLogs("app.services.action_plans.planner", "WARNING") as logs:
            result = self.planner(FakeAgent(error=TimeoutError("payload text"))).suggest(run())
        self.assertEqual(result.source, "rules")
        self.assertTrue(result.plans[0].steps)
        self.assertEqual(self.cache_files(), [])
        self.assertIn("TimeoutError", logs.output[0])
        self.assertNotIn("payload text", logs.output[0])

    def test_invalid_answer_uses_rules(self) -> None:
        with self.assertLogs("app.services.action_plans.planner", "WARNING"):
            result = self.planner(FakeAgent(answer={"plans": []})).suggest(run())
        self.assertEqual(result.source, "rules")
        self.assertEqual(self.cache_files(), [])

    def test_not_configured_never_calls_the_agent(self) -> None:
        agent = FakeAgent()
        result = self.planner(agent, configured=False).suggest(run())
        self.assertEqual(result.source, "rules")
        self.assertEqual(agent.payloads, [])

    def test_unfinished_run_is_rejected(self) -> None:
        for status in ("running", "failed"):
            with self.subTest(status), self.assertRaises(ValueError):
                self.planner().suggest(run(status))

    def test_no_gaps_means_no_plan(self) -> None:
        agent = FakeAgent()
        result = self.planner(agent).suggest(run(priorities={"testing": None}))
        self.assertEqual((result.plans, result.uncovered_skill_ids), ([], []))
        self.assertEqual(agent.payloads, [])


class EnrichTest(PlannerTestCase):
    def test_cards_and_python_totals(self) -> None:
        result = self.planner().suggest(run())
        [plan] = result.plans
        self.assertEqual(plan.steps[0].resource.title, "Cs_Design")
        self.assertEqual(plan.alongside[0].resource.type, "student_org")
        self.assertEqual(plan.covered_skill_ids, ["system_design", "testing", "cloud", "security"])
        self.assertEqual(plan.project_hours, 42)  # p_design 30 + p_test 12
        self.assertEqual(result.uncovered_skill_ids, [])
        self.assertEqual((result.skill_gap_run_id, result.mode, result.job_family),
                         (RUN_ID, "full", "software_engineer"))

    def test_uncovered_gaps_are_listed(self) -> None:
        answer = {"plans": [{**AGENT_ANSWER["plans"][0], "steps": [step("p_design", ["system_design"])],
                             "alongside": []}]}
        # Minimums are filled from the candidates, so remove security's only candidate.
        def without_security(*_args) -> Sources:
            sources = fake_sources()
            return Sources(resources=[c for c in CARDS if c["id"] != "cert_sec"], projects=sources.projects,
                           certifications=[], project_picks=sources.project_picks,
                           certification_picks=sources.certification_picks)

        result = self.planner(FakeAgent(answer=answer), sources=without_security).suggest(run())
        self.assertEqual(result.uncovered_skill_ids, ["security"])



class StageEventTest(PlannerTestCase):
    def stages(self, planner: ActionPlanner, **options) -> list[dict]:
        events: list[dict] = []
        planner.suggest(run(), on_event=events.append, **options)
        return events

    def test_agent_run_reports_each_stage_in_order(self) -> None:
        events = self.stages(self.planner())
        self.assertEqual([event["stage"] for event in events], ["gaps", "candidates", "agent", "checking"])
        self.assertTrue(all(event["type"] == "stage" for event in events))
        self.assertEqual([gap["skill_id"] for gap in events[0]["gaps"]],
                         ["system_design", "testing", "cloud", "security"])
        self.assertEqual(events[1]["counts"], {"project": 3, "certification": 1, "school_course": 1,
                                               "online_course": 1, "student_org": 1})

    def test_cached_run_skips_the_agent_stages(self) -> None:
        planner = self.planner()
        planner.suggest(run())
        self.assertEqual([event["stage"] for event in self.stages(planner)], ["gaps", "candidates", "cached"])

    def test_fallbacks_report_rules(self) -> None:
        with self.assertLogs("app.services.action_plans.planner", "WARNING"):
            failed = self.stages(self.planner(FakeAgent(error=TimeoutError())))
        self.assertEqual([event["stage"] for event in failed], ["gaps", "candidates", "agent", "rules"])
        unconfigured = self.stages(self.planner(configured=False))
        self.assertEqual([event["stage"] for event in unconfigured], ["gaps", "candidates", "rules"])

    def test_samples_take_each_type_in_turn_and_carry_only_catalog_fields(self) -> None:
        samples = self.stages(self.planner())[1]["samples"]
        self.assertEqual([sample["type"] for sample in samples[:5]],
                         ["project", "certification", "school_course", "online_course", "student_org"])
        self.assertTrue(all(set(sample) == {"title", "type"} for sample in samples))

    def test_no_events_when_there_are_no_gaps(self) -> None:
        events: list[dict] = []
        self.planner().suggest(run(priorities={"testing": None}), on_event=events.append)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
