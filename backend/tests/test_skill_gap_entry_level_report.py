"""Keep evidence and pending scores compatible with the web and storage contracts."""

import json
from pathlib import Path
import unittest
from uuid import UUID

from jsonschema import Draft202012Validator

from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.entry_level_report import build_report, score_demand_coverage
from app.services.skill_gaps.match import summarize_match
from app.services.skill_gaps.persistence import result_rows
from app.services.skill_gaps.skill_groups import GROUP_SKILLS
from app.services.skill_gaps.sources import build_sources


FAMILY = "software_engineer"
RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")


class EntryLevelReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
        cls.market = json.loads((ASSET_ROOT / "market_snapshot.json").read_text(encoding="utf-8"))
        repository = Path(__file__).resolve().parents[2]
        schema = json.loads((repository / "docs/contracts/skill-gap-run-storage.schema.json").read_text(encoding="utf-8"))
        cls.report_validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/Report"})

    def setUp(self):
        self.sources = build_sources({"projects": [{"name": "Library API", "content": [
            "Implemented a Python reservation endpoint. Tested it with two conflicting bookings.",
            "Prepared a report for possible container adoption.",
        ]}]})
        groups = GROUP_SKILLS[FAMILY]
        self.assessments = {
            group: {"job_family": FAMILY, "branch": group, "skills": [
                {"skill_id": skill, "entry_level_score": 0, "entry_level_grade": "F",
                 "calculation_state": "scored", "critical_cap_applied": False, "errors": [],
                 "criterion_audits": [
                     {"criterion_id": cid, "status": "not_evidenced", "basis": "none", "weight": weight,
                      "points": 0, "proofs": []}
                     for cid, weight in (("c1", .5), ("c2", .3), ("c3", .2))
                 ]}
                for skill in skills
            ], "citation_review": {"group_blocking_errors": []}}
            for group, skills in groups.items()
        }

    def report(self):
        return build_report(FAMILY, self.assessments, self.catalog, self.market, self.sources)

    def row(self, sid):
        return next(row for assessment in self.assessments.values() for row in assessment["skills"]
                    if row["skill_id"] == sid)

    def test_partial_result_excludes_pending_proofs_and_keeps_exact_display_and_store_spans(self):
        programming = self.row("programming")
        programming.update(entry_level_score=.7, entry_level_grade="B+")
        programming["criterion_audits"][0].update(status="supported", basis="practice", points=1,
            proofs=[{"unit_id": "e001", "quote": "Implemented a Python reservation endpoint"}])
        programming["criterion_audits"][2].update(status="supported", basis="practice", points=1,
            proofs=[{"unit_id": "e001", "quote": "Tested it with two conflicting bookings"}])
        containers = self.row("containers")
        containers.update(entry_level_score=None, entry_level_grade=None, calculation_state="needs_confirmation",
                          errors=["c1:unknown_proof_id"])
        containers["criterion_audits"][0].update(status="supported", basis="practice", points=1,
            proofs=[{"unit_id": "e002", "quote": "Prepared a report"}])
        report = self.report()
        self.report_validator.validate(report)
        self.assertEqual(report["unscored_skill_ids"], ["containers"])
        self.assertEqual(report["reference_validation"]["status"], "partial")
        self.assertNotIn("e002", report["source_index"])
        self.assertNotIn("containers", report["priority_order"])
        self.assertEqual(summarize_match(report)["unscored_skill_count"], 1)
        self.assertLess(score_demand_coverage(report), 1)
        stored = {row["skill_id"]: row for row in result_rows(
            report, None, run_id=RUN_ID, user_id=USER_ID, job_family=FAMILY)}
        self.assertIsNone(stored["containers"]["evidence_strength"])
        self.assertEqual(stored["containers"]["evidence"], [])
        self.assertEqual([item["role"] for item in stored["programming"]["evidence"]], ["capability", "check"])
        for item in stored["programming"]["evidence"]:
            source = report["source_index"][item["unit_id"]]
            self.assertEqual(source["text"][item["start"]:item["end"]], item["quote"])

    def test_report_rejects_group_blocker_and_nonmatching_positive_quote(self):
        found = self.assessments["foundation"]
        found["citation_review"]["group_blocking_errors"] = ["duplicate_proof_id"]
        with self.assertRaisesRegex(ValueError, "failed scope or evidence validation"):
            self.report()
        found["citation_review"]["group_blocking_errors"] = []
        programming = self.row("programming")
        programming.update(entry_level_score=.5, entry_level_grade="C")
        programming["criterion_audits"][0].update(status="supported", basis="practice", points=1,
            proofs=[{"unit_id": "e001", "quote": "Built an unsupported widget"}])
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self.report()
