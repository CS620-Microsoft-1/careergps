"""Deterministic production rubric and citation contracts; no Azure calls.

These fixtures explicitly nominate source units so scoring tests do not depend
on the selector's lexical heuristics. Selector integration has separate tests.
Agent judgments are supplied, not semantically verified by these tests.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from app.services.skill_gaps import entry_level
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.entry_level import _rubric
from app.services.skill_gaps.input import prepare
from app.services.skill_gaps.skill_groups import make_group_payloads
from app.services.skill_gaps.sources import build_index


PROGRAMMING = [
    "Implemented a Python function to validate reservation requests.",
    "Used a dictionary keyed by reservation ID to reject repeated requests.",
    "Tested two duplicate requests and verified that only one reservation was accepted.",
]


def make_case(family="software_engineer", group="foundation", *, projects=None, permissions=None):
    """Build an authentic signed payload with a deliberately fixed shortlist."""
    catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8-sig"))
    projects = projects if projects is not None else [{"name": "Reservation API", "content": PROGRAMMING}]
    base = prepare(family, {"projects": projects}, "rule-fixture", catalog)
    original = make_group_payloads(base)[group]
    _, rules = _rubric._rule_cards(group, family, "rules")
    index = build_index(base["resume_sources"])
    claims = [uid for uid, unit in index.items() if unit["kind"] == "claim"]
    packets = {sid: {
        "unit_ids": list(index), "workload_id": "fixed-rule-fixture",
        "linkage_policy": rules[sid]["linkage_policy"],
        "criterion_unit_ids": {cid: list(claims) for cid in _rubric.CRITERION_IDS},
    } for sid in original["evidence_scope"]["assigned_skill_ids"]}
    for sid, overrides in (permissions or {}).items():
        packets[sid]["criterion_unit_ids"].update(overrides)
    packet = {"version": _rubric.PACKET_VERSION, "job_family": family,
              "source_sha256": _rubric.sha(base["resume_sources"]), "skills": packets}
    payload = entry_level._adapter(group, family).build_payload(original, packet)
    diagnostics = {"skills": {sid: {"search_incomplete": False} for sid in packets}}
    return payload, diagnostics, entry_level.absent_group_output(payload)


def add_proof(output, uid, quote):
    pid = f"p{len(output['proofs']) + 1}"
    output["proofs"].append({"proof_id": pid, "unit_id": uid, "quote": quote})
    return pid


def set_criterion(output, sid, cid, status, *, uid=None, quote=None):
    record = next(item for item in output["result"][sid]["criteria"] if item["criterion_id"] == cid)
    record.update(status=status, basis="none" if status == "not_evidenced" else
                  "unclear" if status == "uncertain" else "practice", proof_ids=[])
    if uid is not None:
        record["proof_ids"] = [add_proof(output, uid, quote)]
    return record


def assess_case(case):
    payload, diagnostics, output = case
    assessment, _ = entry_level.assess(payload["evidence_scope"]["branch"], output, payload, diagnostics)
    return assessment


def skill_row(assessment, sid):
    return next(row for row in assessment["skills"] if row["skill_id"] == sid)


class EntryLevelRuleTests(unittest.TestCase):
    def test_criterion_weights_and_independent_children(self):
        for statuses, expected in [
            (("supported", "not_evidenced", "not_evidenced"), .5),
            (("supported", "supported", "not_evidenced"), .8),
            (("supported", "not_evidenced", "supported"), .7),
            (("supported", "supported", "supported"), 1.0),
        ]:
            with self.subTest(statuses=statuses):
                case = make_case()
                for i, status in enumerate(statuses):
                    if status == "supported":
                        set_criterion(case[2], "programming", f"c{i + 1}", status,
                                      uid=f"e00{i + 1}", quote=PROGRAMMING[i])
                row = skill_row(assess_case(case), "programming")
                self.assertEqual(row["errors"], [])
                self.assertEqual(row["entry_level_score"], expected)
                self.assertEqual(row["calculation_state"], "scored")

    def test_allowed_partial_check_contributes_ten_points(self):
        case = make_case(projects=[{"name": "Reservation API", "content": PROGRAMMING[:2] + [
            "Tested the reservation function."]}])
        for i in range(2):
            set_criterion(case[2], "programming", f"c{i + 1}", "supported", uid=f"e00{i + 1}", quote=PROGRAMMING[i])
        set_criterion(case[2], "programming", "c3", "partial", uid="e003", quote="Tested the reservation function.")
        row = skill_row(assess_case(case), "programming")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], .9)

    def test_allowed_partial_pipeline_method_contributes_fifteen_points(self):
        lines = ["I operated a repeatable data flow.", "The flow moved source records to the reporting store."]
        case = make_case("ai_engineer", projects=[{"name": "Data flow", "content": lines}])
        set_criterion(case[2], "data_pipelines", "c1", "supported", uid="e001", quote=lines[0])
        set_criterion(case[2], "data_pipelines", "c2", "partial", uid="e002", quote=lines[1])
        row = skill_row(assess_case(case), "data_pipelines")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], .65)

    def test_forbidden_partial_core_is_pending_not_half_credit(self):
        case = make_case()
        set_criterion(case[2], "programming", "c1", "partial", uid="e001", quote=PROGRAMMING[0])
        row = skill_row(assess_case(case), "programming")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("c1:partial_disabled_by_rule", row["errors"])

    def test_critical_cap_with_explicit_allowed_partial_core_rule_fixture(self):
        # Shipped cards disable generic partial cores. Exercise the reusable cap
        # with a hypothetical allowed-core rule, without relaxing production data.
        document = deepcopy(_rubric._rule_document("software_engineer"))
        core = document["skills"]["programming"]["criteria"][0]
        core.update(partial_allowed=True, partial_when="Synthetic cap boundary fixture.", partial_disabled_reason=None)
        original_rule_document = _rubric._rule_document
        with patch.object(_rubric, "_rule_document", side_effect=lambda family:
                          document if family == "software_engineer" else original_rule_document(family)):
            case = make_case()
            for i, status in enumerate(("partial", "supported", "supported")):
                set_criterion(case[2], "programming", f"c{i + 1}", status, uid=f"e00{i + 1}", quote=PROGRAMMING[i])
            row = skill_row(assess_case(case), "programming")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], .6)
        self.assertTrue(row["critical_cap_applied"])

    def test_complete_search_without_evidence_is_zero(self):
        row = skill_row(assess_case(make_case()), "programming")
        self.assertEqual(row["entry_level_score"], 0)
        self.assertEqual(row["calculation_state"], "scored")

    def test_incomplete_search_without_evidence_is_pending(self):
        case = make_case()
        case[1]["skills"]["programming"]["search_incomplete"] = True
        row = skill_row(assess_case(case), "programming")
        self.assertIsNone(row["entry_level_score"])
        self.assertEqual(row["selection_review"]["reason"], "candidate_selection_incomplete")

    def test_uncertain_ownership_is_pending_not_zero(self):
        case = make_case()
        set_criterion(case[2], "programming", "c1", "uncertain", uid="e001", quote=PROGRAMMING[0])
        row = skill_row(assess_case(case), "programming")
        self.assertIsNone(row["entry_level_score"])
        self.assertEqual(row["calculation_state"], "needs_confirmation")

    def test_dependent_credit_without_core_is_rejected(self):
        case = make_case()
        set_criterion(case[2], "programming", "c2", "supported", uid="e002", quote=PROGRAMMING[1])
        row = skill_row(assess_case(case), "programming")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("c2:dependent_criterion_without_practice_core", row["errors"])

    def test_cross_project_practice_cannot_be_assembled(self):
        case = make_case(projects=[
            {"name": "Reservation API", "content": PROGRAMMING[:1]},
            {"name": "Other API", "content": PROGRAMMING[1:2]},
        ])
        set_criterion(case[2], "programming", "c1", "supported", uid="e001", quote=PROGRAMMING[0])
        set_criterion(case[2], "programming", "c2", "supported", uid="e002", quote=PROGRAMMING[1])
        row = skill_row(assess_case(case), "programming")
        self.assertIsNone(row["entry_level_score"])
        self.assertEqual(row["selection_review"]["reason"], "cross_activity_practice_evidence")
        self.assertEqual(row["selection_review"]["credited_activity_ids"], ["a001", "a002"])

    def test_inexact_quote_withholds_only_affected_skill(self):
        case = make_case()
        set_criterion(case[2], "programming", "c1", "supported", uid="e001", quote="Invented Rust service.")
        assessment = assess_case(case)
        self.assertIsNone(skill_row(assessment, "programming")["entry_level_score"])
        self.assertEqual(skill_row(assessment, "algorithms")["entry_level_score"], 0)
        self.assertEqual(assessment["citation_review"]["localized_skill_ids"], ["programming"])
        self.assertEqual(assessment["citation_review"]["group_blocking_errors"], [])

    def test_unknown_proof_id_withholds_only_affected_skill(self):
        case = make_case()
        criterion = set_criterion(case[2], "programming", "c1", "supported")
        criterion["proof_ids"] = ["p99"]
        assessment = assess_case(case)
        self.assertIsNone(skill_row(assessment, "programming")["entry_level_score"])
        self.assertEqual(assessment["citation_review"]["localized_skill_ids"], ["programming"])
        self.assertEqual(assessment["citation_review"]["group_blocking_errors"], [])

    def test_exact_quote_outside_criterion_permission_is_rejected(self):
        case = make_case(permissions={"programming": {"c2": []}})
        set_criterion(case[2], "programming", "c1", "supported", uid="e001", quote=PROGRAMMING[0])
        set_criterion(case[2], "programming", "c2", "supported", uid="e002", quote=PROGRAMMING[1])
        assessment = assess_case(case)
        row = skill_row(assessment, "programming")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("c2:proof_outside_fixed_criterion_candidates", row["errors"])
        self.assertEqual(assessment["citation_review"]["group_blocking_errors"], [])

    def test_duplicate_proof_id_blocks_group(self):
        case = make_case()
        set_criterion(case[2], "programming", "c1", "supported", uid="e001", quote=PROGRAMMING[0])
        case[2]["proofs"].append({"proof_id": "p1", "unit_id": "e002", "quote": PROGRAMMING[1]})
        assessment = assess_case(case)
        self.assertIn("duplicate_proof_id", assessment["citation_review"]["group_blocking_errors"])

    def test_unknown_source_unit_blocks_group(self):
        case = make_case()
        set_criterion(case[2], "programming", "c1", "supported", uid="e999", quote=PROGRAMMING[0])
        assessment = assess_case(case)
        self.assertIsNone(skill_row(assessment, "programming")["entry_level_score"])
        self.assertTrue(assessment["citation_review"]["group_blocking_errors"])


if __name__ == "__main__":
    unittest.main()
