"""Offline contract, reference integrity and explicit-live boundary checks."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from app.services.skill_gaps.skill_groups import make_group_payloads
from app.services.skill_gaps.input import prepare
from experiments.entry_level_skill_gaps.entry_agents import entry_contract as entry
from experiments.entry_level_skill_gaps.entry_agents import compact_contract as compact
from experiments.entry_level_skill_gaps.entry_agents import run_experiment as runner
from experiments.entry_level_skill_gaps.entry_agents.manage_agents import build_plan, create_new

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]

class EntryContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((BACKEND / "app/services/skill_gaps/data/core_catalog.json").read_text(encoding="utf-8"))
        self.criteria = {"version": "test.v1", "families": {}}
        for family, record in self.catalog["families"].items():
            self.criteria["families"][family] = {}
            for module in record["modules"]:
                for skill in module["skills"]:
                    self.criteria["families"][family][skill["skill_id"]] = {"criteria": [
                        {"id": f"c{i}", "description": "Demonstrate relevant personal work.",
                         "minimum_evidence": "practice", "critical": i == 1, "weight": 1} for i in (1, 2, 3)]}
        full = prepare("ai_engineer", {"projects": [
            {"name": "First", "content": ["I implemented a Python parser and checked malformed records."]},
            {"name": "Second", "content": ["I implemented another Python parser."]}],
            "technical_skills": ["Python"]}, "offline-test", self.catalog)
        self.payload = entry.build_payload(make_group_payloads(full)["foundation"], self.criteria)
        self.output = {"task": "assess_entry_level_readiness", "result": {"job_family": "ai_engineer"}}
        for skill in self.payload["evidence_scope"]["assigned_skill_ids"]:
            self.output["result"][skill] = {"evidence": {"kind": "absent"}, "entry_level_assessment": {"criteria": [
                {"criterion_id": f"c{i}", "status": "not_evidenced", "proofs": [], "reason_code": "missing_evidence"}
                for i in (1, 2, 3)]}}
        self.units = [unit for source in self.payload["resume_sources"] for unit in source["units"]]
        self.claims = [unit for unit in self.units if unit["kind"] == "claim"]
        self.listed = next(unit for unit in self.units if unit["kind"] == "listed")

    def positive(self):
        unit = self.claims[0]
        record = self.output["result"]["python"]
        record["evidence"] = {"kind": "practice", "operation_id": unit["id"],
            "capability": {"relation": "direct_personal", "quote": "implemented a Python parser"},
            "application": "concrete_action", "method": None, "validation": None}
        for item in record["entry_level_assessment"]["criteria"]:
            item.update(status="supported", proofs=[{"unit_id": unit["id"], "quote": unit["text"]}], reason_code="meets_criterion")
        return record

    def row(self):
        report = entry.assess_output(self.output, self.payload, self.catalog, self.criteria)
        return next(r for r in report["skills"] if r["skill_id"] == "python")

    def test_supported_criteria_score_a_and_evidence_remains_lossless(self):
        record = self.positive()
        original = deepcopy(record["evidence"])
        self.assertEqual(1.0, self.row()["entry_level_score"])
        self.assertEqual("A", self.row()["entry_level_grade"])
        self.assertEqual(original, entry.unpack_output(self.output)["result"]["python"])

    def test_absence_is_zero_not_unavailable(self):
        row = self.row()
        self.assertEqual(0, row["entry_level_score"])
        self.assertEqual("F", row["entry_level_grade"])

    def test_partial_critical_cannot_be_offset_by_other_supported_criteria(self):
        record = self.positive()
        record["entry_level_assessment"]["criteria"][0]["status"] = "partial"
        row = self.row()
        self.assertEqual(0.6, row["entry_level_score"])
        self.assertTrue(row["critical_cap_applied"])

    def test_uncertain_criterion_makes_whole_skill_pending(self):
        record = self.positive()
        record["entry_level_assessment"]["criteria"][2]["status"] = "uncertain"
        self.assertIsNone(self.row()["entry_level_score"])

    def test_literal_quote_integrity_is_required(self):
        record = self.positive()
        record["entry_level_assessment"]["criteria"][1]["proofs"][0]["quote"] = "A result that was never reported."
        self.assertIn("c2:quote_not_exact", self.row()["errors"])
        self.assertIsNone(self.row()["entry_level_score"])

    def test_listed_skill_cannot_prove_practice(self):
        record = self.positive()
        record["entry_level_assessment"]["criteria"][0]["proofs"] = [{"unit_id": self.listed["id"], "quote": self.listed["text"]}]
        self.assertIn("c1:ineligible_proof_kind", self.row()["errors"])

    def test_duplicate_criterion_ids_are_rejected(self):
        record = self.positive()
        record["entry_level_assessment"]["criteria"][1]["criterion_id"] = "c1"
        self.assertIn("criterion_ids_missing_duplicate_or_out_of_order", self.row()["errors"])

    def test_claimed_practice_cannot_coexist_with_knowledge_only_core(self):
        record = self.positive()
        record["evidence"] = {"kind": "knowledge", "evidence_id": self.listed["id"]}
        self.assertIn("c1:practice_criterion_without_practice_core", self.row()["errors"])

    def test_same_criterion_cannot_splice_practice_across_activities(self):
        record = self.positive()
        unit = self.claims[1]
        record["entry_level_assessment"]["criteria"][1]["proofs"].append({"unit_id": unit["id"], "quote": unit["text"]})
        self.assertIn("c2:cross_activity_practice_criterion", self.row()["errors"])

    def test_wrong_family_or_extra_skill_is_not_accepted(self):
        self.positive()
        self.output["result"]["job_family"] = "data_analyst"
        self.assertIn("entry_schema_invalid", self.row()["errors"])

    def test_existing_v12_evidence_errors_block_entry_scoring(self):
        record = self.positive()
        record["evidence"]["operation_id"] = "unknown"
        self.assertIn("original_evidence_invalid", self.row()["errors"])

    def test_frozen_criteria_cannot_be_changed_in_payload(self):
        self.payload["entry_level_criteria"]["skills"]["python"]["criteria"][0]["weight"] = 999
        with self.assertRaises(ValueError):
            self.row()

    def test_contract_is_valid_for_all_groups_and_prompt_removes_old_output(self):
        for group in ("foundation", "lifecycle", "systems"):
            format_ = entry.build_format(self.catalog, group, self.criteria)
            Draft202012Validator.check_schema(format_["schema"])
            text = (BACKEND / f"app/prompts/skill_gaps/skill_groups/{group}/Instructions.md").read_text(encoding="utf-8")
            instructions = entry.build_instructions(text, group)
            self.assertNotIn("performs the unchanged validation and scoring", instructions)
            self.assertIn("ENTRY-LEVEL READINESS", instructions)
            self.assertIn("Do not relabel knowledge as practice", instructions)



class CompactTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((BACKEND / "app/services/skill_gaps/data/core_catalog.json").read_text(encoding="utf-8"))
        self.criteria = json.loads((HERE / "criteria.json").read_text(encoding="utf-8"))
        full = prepare("ai_engineer", {"projects": [
            {"name": "First", "content": ["I implemented a Python parser and checked malformed records."]},
            {"name": "Second", "content": ["I diagnosed memory use in a different workload."]}],
            "technical_skills": ["Python"]}, "offline-test", self.catalog)
        self.payload = compact.build_payload(make_group_payloads(full)["foundation"], self.criteria)
        self.units = [u for s in self.payload["resume_sources"] for u in s["units"]]
        self.claims = [u for u in self.units if u["kind"] == "claim"]
        self.listed = next(u for u in self.units if u["kind"] == "listed")
        self.output = {"task": "assess_entry_level_readiness", "proofs": [], "result": {"job_family": "ai_engineer"}}
        for skill in self.payload["evidence_scope"]["assigned_skill_ids"]:
            self.output["result"][skill] = {"criteria": [
                {"criterion_id": c["id"], "status": "not_evidenced", "basis": "none", "proof_ids": []}
                for c in self.criteria["families"]["ai_engineer"][skill]["criteria"]]}

    def positive(self):
        unit = self.claims[0]
        self.output["proofs"] = [{"proof_id": "p1", "unit_id": unit["id"], "quote": unit["text"]}]
        record = self.output["result"]["python"]
        for c in record["criteria"]:
            c.update(status="supported", basis="practice", proof_ids=["p1"])
        return record

    def row(self, skill="python"):
        report = compact.assess_output(self.output, self.payload, self.catalog, self.criteria)
        return next(r for r in report["skills"] if r["skill_id"] == skill)

    def test_all_supported_reuses_one_proof_and_scores_a(self):
        self.positive()
        row = self.row()
        self.assertEqual(1.0, row["entry_level_score"])
        self.assertEqual("A", row["entry_level_grade"])
        self.assertEqual(1, len(self.output["proofs"]))

    def test_numeric_policy_exactly_unchanged(self):
        old = json.loads((HERE / "scoring_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(old, compact.POLICY)
        record = self.positive()
        record["criteria"][0]["status"] = "partial"
        row = self.row()
        self.assertEqual(0.6, row["entry_level_score"])
        self.assertTrue(row["critical_cap_applied"])

    def test_missing_check_keeps_frozen_weights(self):
        record = self.positive()
        record["criteria"][2].update(status="not_evidenced", basis="none", proof_ids=[])
        self.assertEqual(0.8, self.row()["entry_level_score"])
        self.assertEqual("A-", self.row()["entry_level_grade"])

    def test_all_absent_zero_is_not_unknown(self):
        self.assertEqual(0, self.row()["entry_level_score"])
        self.assertEqual("F", self.row()["entry_level_grade"])

    def test_uncertain_leaves_entire_skill_pending(self):
        record = self.positive()
        record["criteria"][2].update(status="uncertain", basis="unclear")
        self.assertIsNone(self.row()["entry_level_score"])

    def test_unknown_quote_and_id_block_positive_scoring(self):
        self.positive()
        self.output["proofs"][0]["quote"] = "invented quote"
        self.assertIn("c1:quote_not_exact", self.row()["errors"])
        self.output["result"]["python"]["criteria"][0]["proof_ids"] = ["p404"]
        self.assertIn("c1:unknown_proof_id", self.row()["errors"])

    def test_listed_name_cannot_support_personal_practice(self):
        self.positive()
        self.output["proofs"][0].update(unit_id=self.listed["id"], quote=self.listed["text"])
        self.assertIn("c1:ineligible_proof_kind", self.row()["errors"])

    def test_knowledge_basis_cannot_support_practice_criterion(self):
        record = self.positive()
        record["criteria"][0]["basis"] = "knowledge"
        self.assertIn("c1:practice_criterion_without_personal_practice_basis", self.row()["errors"])

    def test_duplicate_proof_ids_are_ambiguous(self):
        self.positive()
        self.output["proofs"].append(deepcopy(self.output["proofs"][0]))
        self.assertIn("c1:duplicate_proof_id", self.row()["errors"])

    def test_duplicate_criterion_ids_rejected(self):
        record = self.positive()
        record["criteria"][1]["criterion_id"] = "c1"
        self.assertIn("criterion_ids_missing_duplicate_or_out_of_order", self.row()["errors"])

    def test_same_criterion_cannot_join_different_activities(self):
        record = self.positive()
        u = self.claims[1]
        self.output["proofs"].append({"proof_id": "p2", "unit_id": u["id"], "quote": u["text"]})
        record["criteria"][1]["proof_ids"] = ["p1", "p2"]
        self.assertIn("c2:cross_activity_practice_criterion", self.row()["errors"])

    def test_different_workload_check_cannot_validate_core_example(self):
        record = self.positive()
        u = self.claims[1]
        self.output["proofs"].append({"proof_id": "p2", "unit_id": u["id"], "quote": u["text"]})
        record["criteria"][2]["proof_ids"] = ["p2"]
        self.assertIn("c3:practice_detail_not_linked_to_core_activity", self.row()["errors"])

    def test_detail_cannot_claim_practice_without_core_example(self):
        record = self.positive()
        record["criteria"][0].update(status="not_evidenced", basis="none", proof_ids=[])
        self.assertIn("c2:practice_detail_without_positive_core_example", self.row()["errors"])

    def test_wrong_family_or_extra_skill_rejected(self):
        self.positive()
        self.output["result"]["job_family"] = "data_analyst"
        self.assertIn("wrong_family_or_assigned_skill_scope", self.row()["errors"])

    def test_unused_proof_is_audited_without_changing_supported_score(self):
        self.positive()
        u = self.claims[1]
        self.output["proofs"].append({"proof_id": "p2", "unit_id": u["id"], "quote": u["text"]})
        report = compact.assess_output(self.output, self.payload, self.catalog, self.criteria)
        self.assertEqual(["p2"], report["validation"]["unused_proof_ids"])
        self.assertEqual(1.0, self.row()["entry_level_score"])

    def test_frozen_criteria_payload_is_enforced(self):
        self.payload["entry_level_criteria"]["skills"]["python"]["criteria"][0]["weight"] = 999
        with self.assertRaises(ValueError):
            self.row()

    def test_schema_and_short_single_task_prompt(self):
        for g in ("foundation", "lifecycle", "systems"):
            fmt = compact.build_format(self.catalog, g, self.criteria)
            Draft202012Validator.check_schema(fmt["schema"])
            serialized = json.dumps(fmt)
            self.assertNotIn("CoreEvidence", serialized)
            self.assertNotIn('"entry_level_assessment"', serialized)
            prompt = compact.build_instructions(g)
            self.assertLess(len(prompt), 4500)
            self.assertNotIn("CANDIDATE SELECTION", prompt)
            self.assertIn("Read the complete supplied resume_sources once", prompt)



class RunnerTests(unittest.TestCase):
    def test_live_is_rejected_before_credentials_or_inputs_without_opt_in(self):
        with patch.object(runner, "invoke") as invoke:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                runner.main(["live", "--config", "missing.json", "--input", "missing.json", "--output", "unused"])
        self.assertEqual(2, caught.exception.code)
        invoke.assert_not_called()

    def test_saved_numeric_policy_is_equal_in_both_contracts(self):
        self.assertEqual(entry.POLICY, compact.POLICY)

    def test_live_versions_must_be_pinned(self):
        for version in (None, "latest", "", "0", 1):
            with self.assertRaises(ValueError):
                runner.require_pinned_agent({"name": "example", "version": version})
        runner.require_pinned_agent({"name": "example", "version": "1"})

    def test_output_files_are_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix=".tmp-test-") as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(HERE.resolve()))
            path = Path(folder) / "report.json"
            runner.save_new(path, {"value": 1})
            with self.assertRaises(FileExistsError):
                runner.save_new(path, {"value": 2})
            self.assertEqual({"value": 1}, runner.read(path))

    def test_agent_plan_is_local_and_uses_new_experimental_name(self):
        plan = build_plan("compact", "foundation", "example-deployment", run_id="12345678")
        self.assertEqual("skill-gap-experiment-foundation-compact-12345678", plan["name"])
        self.assertEqual([], plan["definition"]["tools"])
        self.assertEqual("medium", plan["definition"]["reasoning"]["effort"])
        Draft202012Validator.check_schema(plan["definition"]["text"]["format"]["schema"])

    def test_application_agent_names_cannot_be_created(self):
        with self.assertRaises(ValueError):
            build_plan("compact", "foundation", "example", name_prefix="skill-gap-foundation")
        with self.assertRaises(ValueError):
            create_new({"name": "skill-gap-foundation", "definition": {}}, "https://example.invalid")

    def test_weighting_preserves_pending_without_converting_it_to_zero(self):
        market = {"source_fingerprint": "synthetic", "families": {"ai_engineer": {
            "total_job_count": 10, "skills": {
                "python": {"required_job_count": 6, "preferred_only_job_count": 2},
                "llm": {"required_job_count": 1, "preferred_only_job_count": 0}}}}}
        rows = [{"skill_id": "python", "entry_level_score": .8, "entry_level_grade": "A-"},
                {"skill_id": "llm", "entry_level_score": None, "entry_level_grade": None}]
        result = runner.weighted_entry(rows, market, "ai_engineer")
        self.assertEqual(.8, result["match"]["score"])
        self.assertEqual(["llm"], result["unscored_skill_ids"])
        self.assertEqual(.16, result["skills"][0]["priority"])
        self.assertIsNone(result["skills"][1]["priority"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
