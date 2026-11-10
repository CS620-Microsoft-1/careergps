"""Skill-owned extraction contracts and unchanged-score assembly; fully offline."""
from copy import deepcopy
import json
import unittest

from jsonschema import Draft202012Validator

from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.input import prepare
from app.services.skill_gaps.response import calculate_web_report
from app.services.skill_gaps.schema import build_schema
from app.services.skill_gaps.skill_groups import (
    GROUPS, GROUP_SKILLS, PARTITION_POLICY_VERSION, SELECTION_POLICY_VERSION,
    absent_output, build_group_format, group_catalog, make_group_payloads,
    merge_group_outputs, process_group_output, validate_group_output,
)
from app.services.skill_gaps.validation import validate_response


FAMILY = "ai_engineer"
WORK_OPERATION = "Implemented a retrieval service using stored documents."
WORK_METHOD = "Combined retrieved passages with the model input."
RESEARCH_OPERATION = "Fine-tuned a language model using an applied adaptation method."
RESEARCH_METHOD = "Applied low-rank adaptation while training the model."
PROJECT_OPERATION = "Implemented a Python API that processes records."
PROJECT_METHOD = "Parsed records, validated fields, then stored the accepted records."
CHECK = "Checked held-out examples against expected outputs."
FINDING = "The held-out evaluation reported 85 percent accuracy."
REFERENCE = "The earlier model reported 80 percent accuracy."


def read_asset(name):
    return json.loads((ASSET_ROOT / name).read_text(encoding="utf-8"))


def resume():
    return {
        "work_experience": [{"name": "Example service", "content": [
            WORK_OPERATION, WORK_METHOD, CHECK, FINDING, REFERENCE]}],
        "research_experience": [{"name": "Example research", "content": [
            RESEARCH_OPERATION, RESEARCH_METHOD, CHECK, FINDING, REFERENCE]}],
        "projects": [{"name": "Example API", "content": [
            PROJECT_OPERATION, PROJECT_METHOD, CHECK, FINDING, REFERENCE]}],
        "technical_skills": ["SQL", "Python"],
        "research_interests": ["Model adaptation"],
    }


def unit(payload, text, section):
    source = next(s for s in payload["resume_sources"] if s["path"] == f"/{section}/0")
    return next(u for u in source["units"] if u["text"] == text)


def proof(payload, text, section):
    return {"unit_id": unit(payload, text, section)["id"], "quote": text}


def practice(payload, section="research_experience", *, limited=False, validation=False):
    operation, method = {
        "research_experience": (RESEARCH_OPERATION, RESEARCH_METHOD),
        "work_experience": (WORK_OPERATION, WORK_METHOD),
        "projects": (PROJECT_OPERATION, PROJECT_METHOD),
    }[section]
    record = {
        "kind": "limited_practice" if limited else "practice",
        "operation_id": unit(payload, operation, section)["id"],
        "capability": {"relation": "direct_personal", "quote": operation},
        "application": "concrete_action",
        "method": {"kind": "named_method", "proof": proof(payload, method, section)},
        "validation": None,
    }
    if validation:
        record["validation"] = {
            "kind": "observed", "check": proof(payload, CHECK, section),
            "finding": proof(payload, FINDING, section), "finding_type": "measured_value",
            "reference": None, "reported_value": "85", "relation": "same_capability",
        }
    return record


class GroupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_asset("core_catalog.json")

    def setUp(self):
        self.payload = prepare(FAMILY, resume(), "example-resume", self.catalog)
        self.payloads = make_group_payloads(self.payload)

    def test_every_real_family_skill_has_exactly_one_owner(self):
        self.assertEqual(tuple(self.payloads), GROUPS)
        for family, data in self.catalog["families"].items():
            expected = [s["skill_id"] for m in data["modules"] for s in m["skills"]]
            assigned = [s for group in GROUPS for s in GROUP_SKILLS[family][group]]
            self.assertEqual(len(assigned), len(set(assigned)))
            self.assertEqual(set(expected), set(assigned))
            groups = make_group_payloads(prepare(family, resume(), "resume", self.catalog))
            self.assertEqual(sum(len(p["core_skills"]) for p in groups.values()), len(expected))
        self.assertEqual([len(self.payloads[g]["core_skills"]) for g in GROUPS], [8, 8, 7])

    def test_each_group_keeps_all_sections_original_ids_and_source_kinds(self):
        for group, payload in self.payloads.items():
            self.assertEqual(payload["resume_sources"], self.payload["resume_sources"])
            self.assertEqual(payload["evidence_contract"], self.payload["evidence_contract"])
            self.assertEqual(payload["evidence_scope"], {
                "branch": group, "partition_policy_version": PARTITION_POLICY_VERSION,
                "activity_ids": [s["id"] for s in self.payload["resume_sources"]],
                "assigned_skill_ids": [s["skill_id"] for s in payload["core_skills"]],
            })
            self.assertEqual([s for s in self.payload["core_skills"]
                              if s["skill_id"] in GROUP_SKILLS[FAMILY][group]], payload["core_skills"])

    def test_catalog_cards_and_sources_are_copied_without_mutating_other_groups(self):
        original_catalog, original_payload = deepcopy(self.catalog), deepcopy(self.payload)
        scoped = group_catalog(self.catalog, "foundation")
        scoped["families"][FAMILY]["modules"][0]["skills"][0]["definition"] = "Changed copy"
        self.payloads["foundation"]["core_skills"][0]["definition"] = "Changed card"
        self.payloads["foundation"]["resume_sources"][0]["units"][0]["text"] = "Changed source"
        self.assertEqual(self.catalog, original_catalog)
        self.assertEqual(self.payload, original_payload)
        self.assertEqual(self.payloads["systems"]["resume_sources"], original_payload["resume_sources"])

    def test_strict_group_schemas_require_only_owned_skills_in_every_family(self):
        original = deepcopy(self.catalog)
        public = build_schema(self.catalog)
        for group in GROUPS:
            format_ = build_group_format(self.catalog, group)
            self.assertEqual(format_["name"], f"careergps_core_group_{group}_v12")
            self.assertIs(format_["strict"], True)
            schema = format_["schema"]
            Draft202012Validator.check_schema(schema)
            for definition in ("Proof", "Capability", "Method", "Validation", "Absent",
                               "Knowledge", "Practice", "Uncertain", "CoreEvidence"):
                self.assertEqual(schema["$defs"][definition], public["schema"]["$defs"][definition])
            for family in GROUP_SKILLS:
                payload = make_group_payloads(prepare(family, resume(), "resume", self.catalog))[group]
                output = absent_output(payload)
                self.assertFalse(list(Draft202012Validator(schema).iter_errors(output)))
                own_ids = {s["skill_id"] for s in payload["core_skills"]}
                other = next(s for s in GROUP_SKILLS[family][next(g for g in GROUPS if g != group)]
                             if s not in own_ids)
                output["result"][other] = {"kind": "absent"}
                self.assertTrue(list(Draft202012Validator(schema).iter_errors(output)))
                del output["result"][other]
                del output["result"][next(iter(own_ids))]
                self.assertTrue(list(Draft202012Validator(schema).iter_errors(output)))
        self.assertEqual(self.catalog, original)
        self.assertEqual(build_schema(self.catalog), public)

    def test_catalog_drift_cannot_silently_drop_new_renamed_or_duplicate_skills(self):
        for change in ("new", "renamed", "duplicate", "family"):
            with self.subTest(change=change):
                catalog = deepcopy(self.catalog)
                skills = catalog["families"][FAMILY]["modules"][0]["skills"]
                if change == "new":
                    skills.append({"skill_id": "future_core", "skill_name": "Future"})
                elif change == "renamed":
                    skills[0]["skill_id"] = "renamed_core"
                elif change == "duplicate":
                    skills.append(deepcopy(skills[0]))
                else:
                    catalog["families"]["unknown_family"] = deepcopy(catalog["families"][FAMILY])
                with self.assertRaises(ValueError):
                    build_group_format(catalog, "foundation")

    def test_invalid_group_or_incomplete_input_assignment_is_rejected(self):
        with self.assertRaises(ValueError):
            group_catalog(self.catalog, "work")
        with self.assertRaises(ValueError):
            make_group_payloads({**self.payload, "job_family": "unknown_family"})
        for change in ("missing", "duplicate"):
            item = deepcopy(self.payload)
            if change == "missing":
                item["core_skills"].pop()
            else:
                item["core_skills"].append(deepcopy(item["core_skills"][0]))
            with self.assertRaises(ValueError):
                make_group_payloads(item)

    def test_invalid_or_duplicate_source_ids_are_rejected(self):
        payload = deepcopy(self.payload)
        payload["resume_sources"].append(deepcopy(payload["resume_sources"][0]))
        with self.assertRaises(ValueError):
            make_group_payloads(payload)
        payload = deepcopy(self.payload)
        payload["resume_sources"][0]["path"] = "not-an-original-pointer"
        with self.assertRaises(ValueError):
            make_group_payloads(payload)

    def test_assignment_and_source_scope_must_match_before_validation(self):
        for change in ("cards", "scope_skills", "activities", "policy"):
            with self.subTest(change=change):
                payload = deepcopy(self.payloads["foundation"])
                output = absent_output(payload)
                if change == "cards":
                    payload["core_skills"].reverse()
                elif change == "scope_skills":
                    payload["evidence_scope"]["assigned_skill_ids"].pop()
                elif change == "activities":
                    payload["evidence_scope"]["activity_ids"].pop()
                else:
                    payload["evidence_scope"]["partition_policy_version"] = "unknown"
                with self.assertRaises(ValueError):
                    validate_group_output(output, payload, self.catalog)


class GroupAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_asset("core_catalog.json")
        cls.market = read_asset("market_snapshot.json")

    def setUp(self):
        self.payload = prepare(FAMILY, resume(), "example-resume", self.catalog)
        self.payloads = make_group_payloads(self.payload)
        self.outputs = {g: absent_output(p) for g, p in self.payloads.items()}

    def merge(self, outputs=None):
        return merge_group_outputs(FAMILY, self.outputs if outputs is None else outputs,
                                   self.catalog, self.payload["resume_sources"])

    def test_only_assigned_records_are_validated_without_fake_absent_records(self):
        for group, payload in self.payloads.items():
            checks = validate_group_output(self.outputs[group], payload, self.catalog)
            self.assertEqual(checks["status"], "passed")
            self.assertEqual(set(checks["skills"]), set(payload["evidence_scope"]["assigned_skill_ids"]))
            self.assertFalse(checks["unexpected_skill_ids"])
        merged, audit = self.merge()
        self.assertEqual(merged, absent_output(self.payload))
        self.assertEqual(audit["selection_policy_version"], SELECTION_POLICY_VERSION)
        self.assertEqual(len(audit["skills"]), 23)

    def test_all_groups_can_use_work_research_and_project_evidence(self):
        cases = [("foundation", "python", "research_experience"),
                 ("lifecycle", "fine_tuning", "projects"),
                 ("systems", "rag", "work_experience")]
        for group, skill, section in cases:
            self.outputs[group]["result"][skill] = practice(self.payload, section)
        copied = deepcopy(self.outputs)
        merged, audit = self.merge()
        for group, skill, _ in cases:
            self.assertEqual(merged["result"][skill], self.outputs[group]["result"][skill])
            self.assertEqual(audit["skills"][skill]["selected_branch"], group)
        self.assertEqual(self.outputs, copied)

    def test_cross_activity_proof_stays_pending_without_blocking_another_group(self):
        candidate = practice(self.payload)
        candidate["method"]["proof"] = proof(self.payload, WORK_METHOD, "work_experience")
        self.outputs["lifecycle"]["result"]["fine_tuning"] = candidate
        self.outputs["foundation"]["result"]["python"] = practice(self.payload, "projects")
        merged, audit = self.merge()
        self.assertEqual(merged["result"]["fine_tuning"]["kind"], "uncertain")
        errors = audit["branches"]["lifecycle"]["validation"]["skills"]["fine_tuning"]["errors"]
        self.assertIn("cross_activity_reference", [e["code"] for e in errors])
        self.assertEqual(merged["result"]["python"], self.outputs["foundation"]["result"]["python"])
        self.assertEqual(merged["result"]["machine_learning"], {"kind": "absent"})

    def test_invalid_operation_and_noncontiguous_quotes_stay_pending(self):
        for change in ("activity_id", "quote", "ineligible_interest"):
            with self.subTest(change=change):
                outputs = deepcopy(self.outputs)
                candidate = practice(self.payload)
                if change == "activity_id":
                    candidate["operation_id"] = next(s["id"] for s in self.payload["resume_sources"]
                                                     if s["path"] == "/research_experience/0")
                elif change == "quote":
                    candidate["capability"]["quote"] = "Fine-tuned ... using an applied adaptation method"
                else:
                    interest = next(s for s in self.payload["resume_sources"]
                                    if s["path"] == "/research_interests")
                    candidate = {"kind": "knowledge", "evidence_id": interest["units"][0]["id"]}
                outputs["lifecycle"]["result"]["fine_tuning"] = candidate
                merged, audit = self.merge(outputs)
                self.assertEqual(merged["result"]["fine_tuning"]["kind"], "uncertain")
                self.assertTrue(audit["skills"]["fine_tuning"]["blockers"])
                self.assertEqual(merged["result"]["python"], {"kind": "absent"})

    def test_missing_assigned_record_is_pending_without_fabricated_absence(self):
        del self.outputs["lifecycle"]["result"]["fine_tuning"]
        merged, audit = self.merge()
        self.assertEqual(merged["result"]["fine_tuning"]["kind"], "uncertain")
        errors = audit["branches"]["lifecycle"]["validation"]["skills"]["fine_tuning"]["errors"]
        self.assertIn("missing_skill", [e["code"] for e in errors])
        self.assertEqual(merged["result"]["model_training"], {"kind": "absent"})

    def test_unassigned_key_invalidates_only_its_emitting_owner_group(self):
        self.outputs["foundation"]["result"]["fine_tuning"] = practice(self.payload)
        actual = practice(self.payload, validation=True)
        self.outputs["lifecycle"]["result"]["fine_tuning"] = actual
        merged, audit = self.merge()
        self.assertEqual(merged["result"]["fine_tuning"], actual)
        self.assertTrue(all(merged["result"][s]["kind"] == "uncertain"
                            for s in GROUP_SKILLS[FAMILY]["foundation"]))
        self.assertEqual(audit["branches"]["foundation"]["validation"]["unexpected_skill_ids"], ["fine_tuning"])
        self.assertTrue(all(merged["result"][s]["kind"] == "absent"
                            for s in GROUP_SKILLS[FAMILY]["systems"]))

    def test_wrong_task_or_family_cannot_be_hidden_by_valid_evidence_elsewhere(self):
        for change in ("task", "family", "root_extra"):
            outputs = deepcopy(self.outputs)
            if change == "task":
                outputs["systems"]["task"] = "unexpected_task"
            elif change == "family":
                outputs["systems"]["result"]["job_family"] = "data_analyst"
            else:
                outputs["systems"]["unrequested"] = "value"
            merged, _ = self.merge(outputs)
            self.assertTrue(all(merged["result"][s]["kind"] == "uncertain"
                                for s in GROUP_SKILLS[FAMILY]["systems"]))
            self.assertEqual(merged["result"]["python"], {"kind": "absent"})

    def test_non_direct_capability_stays_pending_and_valid_uncertainty_is_preserved(self):
        uncertain = {"kind": "uncertain", "evidence_id": None, "reason": "The source leaves ownership unclear."}
        self.outputs["systems"]["result"]["prompt_engineering"] = deepcopy(uncertain)
        for relation in ("related_context", "unclear", "other_person"):
            self.outputs["foundation"]["result"]["python"] = practice(self.payload, "projects")
            self.outputs["foundation"]["result"]["python"]["capability"]["relation"] = relation
            merged, audit = self.merge()
            self.assertEqual(merged["result"]["python"]["kind"], "uncertain")
            self.assertEqual(merged["result"]["prompt_engineering"], uncertain)
            self.assertEqual(audit["skills"]["prompt_engineering"]["state"], "uncertain")

    def test_normalization_matches_existing_rules_and_is_audited(self):
        record = practice(self.payload, "projects")
        record["capability"]["quote"] = "..." + PROJECT_OPERATION + "..."
        self.outputs["foundation"]["result"]["python"] = record
        old_outputs = deepcopy(self.outputs)
        normalized, processing, checks = process_group_output(
            self.outputs["foundation"], self.payloads["foundation"], self.catalog)
        merged, audit = self.merge()
        self.assertEqual(checks["status"], "passed")
        self.assertGreater(processing["count"], 0)
        self.assertEqual(audit["branches"]["foundation"]["response_processing"], processing)
        self.assertEqual(merged["result"]["python"], normalized["result"]["python"])
        self.assertEqual(self.outputs, old_outputs)

    def test_frozen_evidence_reassembly_retains_entire_public_schema_and_scored_report(self):
        frozen = absent_output(self.payload)
        frozen["result"]["python"] = practice(self.payload, "projects", validation=True)
        frozen["result"]["fine_tuning"] = practice(self.payload, limited=True, validation=True)
        frozen["result"]["prompt_engineering"] = {
            "kind": "uncertain", "evidence_id": None, "reason": "Prompt design is not established."}
        for group in GROUPS:
            self.outputs[group]["result"] = {"job_family": FAMILY, **{
                s["skill_id"]: deepcopy(frozen["result"][s["skill_id"]])
                for s in self.payloads[group]["core_skills"]}}
        original = deepcopy(frozen)
        merged, _ = self.merge()
        self.assertEqual(merged, frozen)
        self.assertEqual(frozen, original)
        self.assertFalse(list(Draft202012Validator(build_schema(self.catalog)["schema"]).iter_errors(merged)))
        self.assertEqual(validate_response(merged, FAMILY, self.payload["resume_sources"], self.catalog)["status"], "passed")
        expected = calculate_web_report(FAMILY, frozen, self.catalog, self.market, self.payload["resume_sources"])
        actual = calculate_web_report(FAMILY, merged, self.catalog, self.market, self.payload["resume_sources"])
        self.assertEqual(actual, expected)
        self.assertEqual(actual["unscored_skill_ids"], ["prompt_engineering"])

    def test_absence_assembly_and_frozen_evidence_work_for_every_family(self):
        for family in GROUP_SKILLS:
            payload = prepare(family, resume(), "resume", self.catalog)
            outputs = {g: absent_output(p) for g, p in make_group_payloads(payload).items()}
            merged, _ = merge_group_outputs(family, outputs, self.catalog, payload["resume_sources"])
            self.assertEqual(merged, absent_output(payload))
            self.assertFalse(list(Draft202012Validator(build_schema(self.catalog)["schema"]).iter_errors(merged)))

    def test_missing_or_extra_group_cannot_be_treated_as_known_absence(self):
        missing = deepcopy(self.outputs)
        del missing["systems"]
        extra = {**self.outputs, "work": self.outputs["foundation"]}
        for outputs in (missing, extra):
            with self.assertRaises(ValueError):
                self.merge(outputs)

    def test_known_empty_resume_can_assemble_only_assigned_absence_records(self):
        payload = prepare(FAMILY, {}, "resume", self.catalog)
        self.assertEqual(payload["resume_sources"], [])
        outputs = {g: absent_output(p) for g, p in make_group_payloads(payload).items()}
        merged, _ = merge_group_outputs(FAMILY, outputs, self.catalog, [])
        self.assertEqual(merged, absent_output(payload))


if __name__ == "__main__":
    unittest.main()
