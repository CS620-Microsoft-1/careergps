import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.schemas.certifications import Certification
from app.services.action_plans import candidates as module
from app.services.action_plans.candidates import (
    Picks, Sources, agent_payload, build_candidates, cached_project_picks, gaps_from_report, load_sources,
)

RUN_ID = "0123456789abcdef0123456789abcdef"
FAMILY = "software_engineer"
GAPS = [  # highest priority first, as gaps_from_report returns them
    {"skill_id": "system_design", "skill_name": "System design", "skill_gap": 0.8, "skill_gap_grade": "D", "priority": 0.9},
    {"skill_id": "testing", "skill_name": "Testing", "skill_gap": 0.6, "skill_gap_grade": "C", "priority": 0.7},
    {"skill_id": "cloud", "skill_name": "Cloud", "skill_gap": 0.4, "skill_gap_grade": "C", "priority": 0.5},
]


def card(resource_id: str, kind: str, skills: list[str], **extra) -> dict:
    return {"id": resource_id, "type": kind, "title": resource_id.title(), "provider": "P", "meta": "",
            "description": "", "skills": skills, **extra}


def project(resource_id: str, skills: list[str], difficulty: str = "intermediate", hours: int = 20) -> dict:
    return {"id": resource_id, "career_path": "Software Engineering", "title": resource_id, "difficulty": difficulty,
            "estimated_hours": hours, "supported_skill_ids": skills}


def certification(resource_id: str, skills: list[str], level: str = "beginner") -> Certification:
    return Certification(id=resource_id, name=resource_id, provider="P", url="https://example.test", cost_usd=0,
                         cost_note="", level=level, skills={FAMILY: skills}, last_verified="2026-01-01")


def sources(**overrides) -> Sources:
    values = dict(
        resources=[
            card("p_design", "project", ["system_design", "testing"]),
            card("p_test", "project", ["testing"]),
            card("p_other", "project", ["frontend"]),
            card("c_cloud", "certification", ["cloud"]),
            card("c_design", "certification", ["system_design"]),
            card("cs400", "school_course", ["system_design"], school="University of Wisconsin–Madison"),
            card("cs300", "school_course", ["testing"], school="University of Wisconsin–Madison"),
            card("sql101", "online_course", ["testing"]),
            card("madhacks", "student_org", ["cloud"], alongside=True),
        ],
        projects=[project("p_design", ["system_design", "testing"]), project("p_test", ["testing"], "beginner", 10),
                  project("p_other", ["frontend"])],
        certifications=[certification("c_cloud", ["cloud"]), certification("c_design", ["system_design"], "advanced")],
        project_picks=Picks(("p_test",), "project_agent"),
        certification_picks=Picks((), "rules"),
    )
    return Sources(**{**values, **overrides})


def build(**kwargs):
    options = {"taken_course_ids": set(), "done_resource_ids": set(), **kwargs}
    return build_candidates(GAPS, options.pop("sources", sources()), **options)


def by_id(result) -> dict:
    return {item["resource_id"]: item for item in result.items}


class GapsFromReportTest(unittest.TestCase):
    def test_keeps_scored_gaps_in_priority_order(self) -> None:
        skill = lambda sid, gap, priority, strength=0.3: {"skill_id": sid, "skill_name": sid, "skill_gap": gap,
                                                          "skill_gap_grade": "C", "priority": priority,
                                                          "resume_evidence_strength": strength}
        # Same rule as the Gaps page: evidence at or above 0.7 is a strength, not a gap.
        report = {"skills": [skill("low", 0.2, 0.1), skill("none", 0, 0.9), skill("unscored", 0.5, None),
                             skill("high", 0.7, 0.8), skill("strong", 0.1, 0.95, strength=0.7)]}
        self.assertEqual([gap["skill_id"] for gap in gaps_from_report(report)], ["high", "low"])


class BuildCandidatesTest(unittest.TestCase):
    def test_keeps_only_gap_closing_resources_with_trimmed_skills(self) -> None:
        items = by_id(build())
        self.assertNotIn("p_other", items)
        self.assertEqual(items["p_design"]["skill_ids"], ["system_design", "testing"])
        self.assertEqual(items["madhacks"]["skill_ids"], ["cloud"])

    def test_removes_taken_courses_and_done_items_but_keeps_saved_ones(self) -> None:
        items = by_id(build(taken_course_ids={"cs400", "sql101"}, done_resource_ids={"p_test"}))
        self.assertNotIn("cs400", items)
        self.assertNotIn("p_test", items)
        self.assertIn("sql101", items)  # only school courses can be "taken"
        self.assertIn("cs300", items)

    def test_marks_who_suggested_each_candidate(self) -> None:
        picks = Picks(("c_design",), "rules")
        items = by_id(build(sources=sources(certification_picks=picks)))
        self.assertEqual(items["p_test"]["suggested_by"], "project_agent")
        self.assertEqual(items["p_design"]["suggested_by"], "catalog")
        self.assertEqual(items["c_design"]["suggested_by"], "rules")
        self.assertEqual(items["cs400"]["suggested_by"], "catalog")

    def test_difficulty_and_hours_only_where_known(self) -> None:
        items = by_id(build())
        self.assertEqual((items["p_test"]["difficulty"], items["p_test"]["estimated_hours"]), ("beginner", 10))
        self.assertEqual((items["c_design"]["difficulty"], items["c_design"]["estimated_hours"]), ("advanced", None))
        self.assertEqual((items["cs400"]["difficulty"], items["cs400"]["estimated_hours"]), (None, None))
        self.assertTrue(items["madhacks"]["alongside"])
        self.assertFalse(items["cs400"]["alongside"])

    def test_ranks_picks_first_then_gap_priority(self) -> None:
        projects = [item["resource_id"] for item in build().items if item["type"] == "project"]
        self.assertEqual(projects, ["p_test", "p_design"])  # p_test is the project Agent's pick
        certifications = [item["resource_id"] for item in build().items if item["type"] == "certification"]
        self.assertEqual(certifications, ["c_design", "c_cloud"])  # system_design outranks cloud

    def test_easier_difficulty_breaks_ties(self) -> None:
        resources = [card("hard", "project", ["testing"]), card("easy", "project", ["testing"])]
        projects = [project("hard", ["testing"], "advanced"), project("easy", ["testing"], "beginner")]
        result = build(sources=sources(resources=resources, projects=projects, project_picks=Picks((), "rules")))
        self.assertEqual([item["resource_id"] for item in result.items], ["easy", "hard"])

    def test_caps_each_type(self) -> None:
        many = [card(f"p{i:02}", "project", ["testing"]) for i in range(30)]
        courses = [card(f"o{i:02}", "online_course", ["testing"]) for i in range(30)]
        result = build(sources=sources(resources=many + courses, projects=[project(c["id"], ["testing"]) for c in many],
                                       certifications=[]))
        kinds = [item["type"] for item in result.items]
        self.assertEqual(kinds.count("project"), module.PROJECT_CAP)
        self.assertEqual(kinds.count("online_course"), module.OTHER_CAP)

    def test_shortlists_decide_projects_and_certifications(self) -> None:
        # A project card on the Resources list but outside the project Agent's shortlist is not a candidate.
        result = build(sources=sources(projects=[project("p_test", ["testing"])]))
        self.assertNotIn("p_design", by_id(result))

    def test_returns_cards_for_every_candidate(self) -> None:
        result = build()
        self.assertEqual(set(result.resources), {item["resource_id"] for item in result.items})
        self.assertEqual(result.resources["cs400"]["school"], "University of Wisconsin–Madison")


class CachedPicksTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)

    def tearDown(self) -> None:
        self._directory.cleanup()

    def write(self, folder: str, data) -> None:
        (self.root / folder).mkdir(exist_ok=True)
        (self.root / folder / f"{RUN_ID}.json").write_text(json.dumps(data) if not isinstance(data, str) else data)

    def test_reads_agent_picks_in_order(self) -> None:
        self.write("project_recommendations", {"source": "agent", "recommendations": [
            {"project_id": "b"}, {"project_id": "a"}, {"project_id": "b"}]})
        self.assertEqual(cached_project_picks(RUN_ID, self.root), ("b", "a"))

    def test_missing_corrupt_rule_or_bad_id_gives_nothing(self) -> None:
        self.assertEqual(cached_project_picks(RUN_ID, self.root), ())
        self.write("project_recommendations", "{not json")
        self.assertEqual(cached_project_picks(RUN_ID, self.root), ())
        self.write("project_recommendations", {"source": "rules", "recommendations": [{"project_id": "a"}]})
        self.assertEqual(cached_project_picks(RUN_ID, self.root), ())
        self.assertEqual(cached_project_picks("../../etc", self.root), ())


class LoadSourcesTest(unittest.TestCase):
    def patches(self):
        return (patch.object(module, "project_shortlist", return_value=[project("p_test", ["testing"])]),
                patch.object(module, "get_catalog", return_value={}),
                patch.object(module, "for_family", return_value=[certification("c_cloud", ["cloud"])]),
                patch.object(module, "resources_for", return_value=[]),
                patch.object(module, "rank_projects", return_value={"recommendations": [{"project_id": "p_rule"}]}))

    def test_uses_rule_picks_when_no_cache(self) -> None:
        p = self.patches()
        with tempfile.TemporaryDirectory() as directory, p[0], p[1], p[2], p[3], p[4]:
            result = load_sources(FAMILY, None, GAPS, RUN_ID, Path(directory))
        self.assertEqual(result.project_picks, Picks(("p_rule",), "rules"))
        self.assertEqual(result.certification_picks, Picks(("c_cloud",), "rules"))

    def test_prefers_cached_agent_picks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project_recommendations").mkdir()
            (root / "project_recommendations" / f"{RUN_ID}.json").write_text(
                json.dumps({"source": "agent", "recommendations": [{"project_id": "p_test"}]}))
            p = self.patches()
            with p[0] as shortlist, p[1], p[2], p[3], p[4] as rules:
                result = load_sources(FAMILY, None, GAPS, RUN_ID, root)
        self.assertEqual(result.project_picks, Picks(("p_test",), "project_agent"))
        rules.assert_not_called()
        # The project Agent's own shortlist function gets the role and the verified gaps.
        self.assertEqual(shortlist.call_args.args[0], "Software Engineering")
        self.assertEqual([gap["skill_id"] for gap in shortlist.call_args.args[2]], ["system_design", "testing", "cloud"])


class AgentPayloadTest(unittest.TestCase):
    def test_matches_the_step_one_input_shape(self) -> None:
        payload = agent_payload("full", FAMILY, GAPS, build())
        self.assertEqual(set(payload), {"mode", "job_family", "gaps", "candidates"})
        self.assertEqual(payload["gaps"][0], {"skill_id": "system_design", "skill_name": "System design"})
        self.assertEqual(set(payload["candidates"][0]), {"resource_id", "type", "title", "provider", "skill_ids",
                                                         "difficulty", "estimated_hours", "alongside", "suggested_by"})
        json.dumps(payload)  # must be serializable as INPUT_JSON

    def test_docs_example_has_the_same_shape(self) -> None:
        example_path = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "action-plan-input.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        payload = agent_payload("full", FAMILY, GAPS, build())
        self.assertEqual(set(example), set(payload))
        self.assertEqual(set(example["gaps"][0]), set(payload["gaps"][0]))
        gap_ids = {gap["skill_id"] for gap in example["gaps"]}
        for candidate in example["candidates"]:
            with self.subTest(candidate["resource_id"]):
                self.assertEqual(set(candidate), set(payload["candidates"][0]))
                self.assertTrue(set(candidate["skill_ids"]) <= gap_ids)
                self.assertEqual(candidate["alongside"], candidate["type"] == "student_org")


if __name__ == "__main__":
    unittest.main()
