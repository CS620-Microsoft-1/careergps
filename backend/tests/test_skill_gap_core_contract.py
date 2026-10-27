"""Portable scoring and quotation regressions: synthetic data, no model or DB."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from app.services.skill_gaps import scoring_math
from app.services.skill_gaps.scoring import calculate
from app.services.skill_gaps.sources import build_index, build_sources


FAMILY = "software_engineer"
CATALOG = {"families": {FAMILY: {"modules": [{
    "module_id": "delivery", "module_name": "Software delivery", "skills": [{
        "skill_id": "backend_apis", "skill_name": "Backend and API development",
    }],
}]}}}
MARKET = {"source_fingerprint": "fictional-market-v1", "families": {FAMILY: {
    "total_job_count": 10, "skills": {"backend_apis": {
        "required_job_count": 6, "preferred_only_job_count": 2,
        "unspecified_job_count": 1, "required_ratio": .6,
        "preferred_only_ratio": .2, "unspecified_ratio": .1,
    }},
}}}


def practice():
    return {
        "kind": "practice", "operation_id": "e001",
        "capability": {"relation": "direct_personal", "quote": "Built an API"},
        "application": "concrete_action",
        "method": {"kind": "named_method", "proof": {
            "unit_id": "e001", "quote": "request validation",
        }},
        "validation": {"kind": "check_only", "check": {
            "unit_id": "e002", "quote": "Verified invalid requests were rejected.",
        }, "finding": None, "finding_type": None, "reference": None,
            "reported_value": None, "relation": "same_capability"},
    }


def report(record):
    sources = build_sources({"projects": [{"name": "Example API", "content": [
        "Built an API using request validation.",
        "Verified invalid requests were rejected.",
    ]}]})
    output = {"task": "extract_resume_evidence", "result": {
        "job_family": FAMILY, "backend_apis": record,
    }}
    return calculate(FAMILY, output, CATALOG, MARKET, sources)["skills"][0]


class ScoringContractTests(unittest.TestCase):
    def test_points_and_task_cap_across_rubric_categories(self):
        # Independent expected tables make a point change an explicit decision.
        for application, action in [("task_only", 6), ("concrete_action", 9),
                                    ("decision_or_tradeoff", 10)]:
            for method, method_points in [("none", 0), ("named_method", 1),
                                          ("mechanism_described", 3), ("rationale_explained", 5)]:
                for validation, validation_points in [("none", 0), ("method_only", 1),
                                                      ("method_and_result", 3),
                                                      ("comparative_or_repeated", 5)]:
                    with self.subTest(application=application, method=method, validation=validation):
                        item = {"support_relation": "direct", "attribution": "self",
                                "application_detail": application, "method_detail": method,
                                "validation_level": validation}
                        expected = (action + method_points + validation_points) / 20
                        if application == "task_only":
                            expected = min(expected, .45)
                        self.assertEqual(scoring_math.score_item(item)["score"], expected)

    def test_knowledge_absence_partial_and_unknown_are_distinct(self):
        listed = {"support_relation": "direct", "attribution": "self", "application_detail": "listed"}
        self.assertEqual(scoring_math.score_item(listed)["score"], .20)
        full = {"support_relation": "direct", "attribution": "self",
                "application_detail": "decision_or_tradeoff", "method_detail": "rationale_explained",
                "validation_level": "comparative_or_repeated"}
        self.assertEqual(scoring_math.evidence_strength({"status": "partial", "evidence": [full]}), .60)
        self.assertEqual(scoring_math.evidence_strength({"status": "not_evidenced"}), 0)
        self.assertIsNone(scoring_math.evidence_strength({"status": "needs_confirmation"}))

    def test_grade_boundaries(self):
        cases = [("0", "A"), ("0.10", "A"), ("0.100001", "A-"),
                 ("0.20", "A-"), ("0.200001", "B+"), ("0.30", "B+"),
                 ("0.300001", "B"), ("0.40", "B"), ("0.400001", "C"),
                 ("0.60", "C"), ("0.600001", "D"), ("0.999999", "D"), ("1", "F")]
        for gap, expected in cases:
            with self.subTest(gap=gap):
                self.assertEqual(scoring_math.grade(Decimal(gap)), expected)
        self.assertIsNone(scoring_math.grade(None))

    def test_demand_changes_priority_only(self):
        record = practice()
        row = report(record)
        self.assertEqual(row["resume_evidence_strength"], .55)
        self.assertEqual(row["skill_gap"], .45)
        self.assertEqual(row["skill_gap_grade"], "C")
        self.assertEqual(row["priority"], .36)
        other = deepcopy(MARKET)
        other["families"][FAMILY]["skills"]["backend_apis"].update(
            required_job_count=1, preferred_only_job_count=1, unspecified_job_count=8)
        sources = build_sources({"projects": [{"name": "Example API", "content": [
            "Built an API using request validation.", "Verified invalid requests were rejected.",
        ]}]})
        output = {"task": "extract_resume_evidence", "result": {
            "job_family": FAMILY, "backend_apis": record}}
        changed = calculate(FAMILY, output, CATALOG, other, sources)["skills"][0]
        for field in ("resume_evidence_strength", "skill_gap", "skill_gap_grade"):
            self.assertEqual(row[field], changed[field])
        self.assertEqual(changed["priority"], .09)


class SourceIntegrityTests(unittest.TestCase):
    def test_identical_resume_has_stable_ids_independent_of_dictionary_order(self):
        first = {"projects": [{"name": "Example API", "content": ["Built an API."]}],
                 "technical_skills": ["Python"], "personal_information": {"name": "Example Person"}}
        second = {"personal_information": {"name": "Example Person"},
                  "technical_skills": ["Python"],
                  "projects": [{"content": ["Built an API."], "name": "Example API"}]}
        self.assertEqual(build_sources(first), build_sources(second))
        index = build_index(build_sources(first))
        self.assertEqual([unit["text"] for unit in index.values()], ["Built an API.", "Python"])
        self.assertFalse(any("personal_information" in unit["path"] for unit in index.values()))

    def test_exact_reference_is_scored(self):
        self.assertEqual(report(practice())["local_reference_check"]["status"], "passed")

    def test_fake_quote_and_unknown_unit_remain_pending_not_zero(self):
        for mutation, expected_code in [("quote", "quote_not_in_original"),
                                         ("unit", "unknown_evidence_id")]:
            record = practice()
            if mutation == "quote":
                record["capability"]["quote"] = "Invented production performance claim"
            else:
                record["operation_id"] = "e999"
            with self.subTest(mutation=mutation):
                row = report(record)
                self.assertIn(expected_code, [e["code"] for e in row["local_reference_check"]["errors"]])
                for key in ("resume_evidence_strength", "skill_gap", "skill_gap_grade", "priority"):
                    self.assertIsNone(row[key])

    def test_cross_activity_method_is_rejected(self):
        sources = build_sources({"projects": [
            {"name": "First", "content": ["Built an API."]},
            {"name": "Second", "content": ["Used request validation."]},
        ]})
        record = practice()
        record["method"]["proof"]["unit_id"] = "e002"
        record["validation"] = None
        row = calculate(FAMILY, {"task": "extract_resume_evidence", "result": {
            "job_family": FAMILY, "backend_apis": record}}, CATALOG, MARKET, sources)["skills"][0]
        self.assertEqual(row["local_reference_check"]["status"], "needs_confirmation")
        self.assertIsNone(row["resume_evidence_strength"])


class StorageAndProvenanceTests(unittest.TestCase):
    def test_storage_example_uses_real_resume_link_and_validates(self):
        contracts = Path(__file__).resolve().parents[2] / "docs" / "contracts"
        schema = json.loads((contracts / "skill-gap-run-storage.schema.json").read_text(encoding="utf-8"))
        example = json.loads((contracts / "skill-gap-run-storage.example.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)
        self.assertEqual(example["report"]["resume_id"], example["resume_id"])

    def test_market_api_preserves_counts_and_exposes_unknown_coverage(self):
        from app.schemas.skill_gap_web import MarketDemandSnapshot
        from app.services.skill_gaps.assets import ASSET_ROOT
        from app.services.skill_gaps.market import get_market_demand

        stored = json.loads((ASSET_ROOT / "market_snapshot.json").read_text(encoding="utf-8"))
        for family, expected_skills in [("software_engineer", 22), ("data_analyst", 18), ("ai_engineer", 23)]:
            with self.subTest(family=family):
                result = MarketDemandSnapshot.model_validate(get_market_demand(family))
                self.assertEqual(len(result.skills), expected_skills)
                self.assertIsNone(result.posting_window)
                self.assertIsNone(result.company_coverage)
                self.assertTrue(result.coverage_limitations)
                for skill in result.skills:
                    raw = stored["families"][family]["skills"][skill.skill_id]
                    for field, value in raw.items():
                        self.assertEqual(getattr(skill, field), value)


if __name__ == "__main__":
    unittest.main()
