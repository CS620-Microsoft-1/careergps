"""Synthetic regressions for conservative, offline original-reference alignment.

No saved personal resume, model client, database, or ignored run artifact is used.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from app.services.skill_gaps.response import calculate_web_report, normalize_response
from app.services.skill_gaps.sources import build_index, build_sources


FAMILY = "software_engineer"
SKILL = "example_skill"
CATALOG = {"families": {FAMILY: {"modules": [{
    "module_id": "example_module", "module_name": "Example module", "skills": [{
        "skill_id": SKILL, "skill_name": "Example capability",
    }],
}]}}}
MARKET = {"source_fingerprint": "synthetic-alignment-test", "families": {FAMILY: {
    "total_job_count": 10, "skills": {SKILL: {
        "required_job_count": 4, "preferred_only_job_count": 2,
        "unspecified_job_count": 1, "required_ratio": .4,
        "preferred_only_ratio": .2, "unspecified_ratio": .1,
    }},
}}}
OPERATION = "Built a repeatable training service."
METHOD = "Used isolated worker processes."
CHECK = "Checked expected requests and recorded results."


def make_sources(first=None, second=None):
    projects = [{"name": "Fictional project", "content": first or [OPERATION, METHOD, CHECK]}]
    if second is not None:
        projects.append({"name": "Other fictional project", "content": second})
    return build_sources({"projects": projects})


def record():
    return {
        "kind": "practice", "operation_id": "e001",
        "capability": {"relation": "direct_personal", "quote": OPERATION},
        "application": "concrete_action",
        "method": {"kind": "named_method", "proof": {"unit_id": "e002", "quote": METHOD}},
        "validation": {"kind": "check_only", "check": {"unit_id": "e003", "quote": CHECK},
                       "finding": None, "finding_type": None, "reference": None,
                       "reported_value": None, "relation": "same_capability"},
    }


def output(value):
    return {"task": "extract_resume_evidence", "result": {"job_family": FAMILY, SKILL: value}}


def normalized(value, sources=None):
    return normalize_response(FAMILY, output(value), CATALOG, sources or make_sources())


def report(value, sources=None):
    return calculate_web_report(FAMILY, output(value), CATALOG, MARKET, sources or make_sources())


class ReferenceAlignmentTests(unittest.TestCase):
    def assert_scored(self, value, sources=None):
        result = report(value, sources)
        row = result["skills"][0]
        self.assertEqual(row["local_reference_check"]["status"], "passed")
        self.assertIsNotNone(row["resume_evidence_strength"])
        return result, row

    def assert_unchanged_pending(self, value, sources=None):
        original = output(value)
        copied = deepcopy(original)
        next_output, audit = normalize_response(FAMILY, original, CATALOG, sources or make_sources())
        self.assertEqual(original, copied)
        self.assertEqual(next_output, original)
        self.assertEqual(audit["adjustments"], [])
        row = report(value, sources)["skills"][0]
        self.assertEqual(row["local_reference_check"]["status"], "needs_confirmation")
        for field in ("resume_evidence_strength", "skill_gap", "skill_gap_grade", "priority"):
            self.assertIsNone(row[field])

    def test_removes_only_outside_ellipsis_from_unique_original_fragment(self):
        for quote in ("...Checked expected requests", "Checked expected requests...",
                      "...Checked expected requests...", "\u2026Checked expected requests\u2026"):
            with self.subTest(quote=quote):
                value = record()
                value["validation"]["check"]["quote"] = quote
                result, row = self.assert_scored(value)
                self.assertEqual(row["agent_assessment"]["validation"]["check"]["quote"],
                                 "Checked expected requests")
                self.assertEqual(row["original_agent_assessment"], value)
                self.assertTrue(result["response_processing"]["adjustments"])

    def test_restores_sentence_initial_capitalization_using_original_text(self):
        value = record()
        value["method"]["proof"]["quote"] = "used isolated worker processes."
        _, row = self.assert_scored(value)
        self.assertEqual(row["agent_assessment"]["method"]["proof"]["quote"], METHOD)
        self.assertEqual(row["original_agent_assessment"]["method"]["proof"]["quote"],
                         "used isolated worker processes.")

    def test_combines_outside_ellipsis_and_sentence_initial_case(self):
        value = record()
        value["validation"]["check"]["quote"] = "...checked expected requests..."
        result, row = self.assert_scored(value)
        self.assertEqual(row["agent_assessment"]["validation"]["check"]["quote"],
                         "Checked expected requests")
        rules = {rule for change in result["response_processing"]["adjustments"]
                 for rule in change.get("rules", [])}
        self.assertEqual(rules, {"exterior_ellipsis_removed", "sentence_initial_case_restored"})

    def test_format_alignment_accepts_fragment_before_terminal_prose_period(self):
        for target, quote, expected in [
            ("method", "used isolated worker processes", "Used isolated worker processes"),
            ("check", "...Checked expected requests and recorded results",
             "Checked expected requests and recorded results"),
        ]:
            with self.subTest(target=target):
                value = record()
                proof = value["method"]["proof"] if target == "method" else value["validation"]["check"]
                proof["quote"] = quote
                _, row = self.assert_scored(value)
                fixed = row["agent_assessment"]
                after = fixed["method"]["proof"] if target == "method" else fixed["validation"]["check"]
                self.assertEqual(after["quote"], expected)

    def test_unique_sibling_reference_accepts_fragment_before_terminal_prose_period(self):
        value = record()
        value["method"]["proof"] = {"unit_id": "e001", "quote": METHOD.removesuffix(".")}
        _, row = self.assert_scored(value)
        self.assertEqual(row["agent_assessment"]["method"]["proof"],
                         {"unit_id": "e002", "quote": METHOD.removesuffix(".")})

    def test_rebinds_known_wrong_method_unit_within_the_original_activity(self):
        value = record()
        value["method"]["proof"]["unit_id"] = "e001"
        _, row = self.assert_scored(value)
        self.assertEqual(row["agent_assessment"]["method"]["proof"]["unit_id"], "e002")
        self.assertEqual(row["agent_assessment"]["operation_id"], "e001")

    def test_rebinds_operation_when_capability_quote_uniquely_identifies_sibling(self):
        value = record()
        value["operation_id"] = "e002"
        _, row = self.assert_scored(value)
        self.assertEqual(row["agent_assessment"]["operation_id"], "e001")
        self.assertEqual(row["agent_assessment"]["capability"]["quote"], OPERATION)
        self.assertEqual(row["original_agent_assessment"]["operation_id"], "e002")

    def test_keeps_raw_agent_response_and_source_units_immutable(self):
        value = record()
        value["validation"]["check"]["quote"] = "...Checked expected requests"
        raw, sources = output(value), make_sources()
        original_raw, original_sources = deepcopy(raw), deepcopy(sources)
        normalize_response(FAMILY, raw, CATALOG, sources)
        calculate_web_report(FAMILY, raw, CATALOG, MARKET, sources)
        self.assertEqual(raw, original_raw)
        self.assertEqual(sources, original_sources)

    def test_alignment_audit_retains_original_errors_and_exact_source_span(self):
        value = record()
        value["method"]["proof"]["quote"] = "used isolated worker processes."
        sources = make_sources()
        _, audit = normalized(value, sources)
        self.assertGreater(audit["count"], 0)
        index = build_index(sources)
        for adjustment in audit["adjustments"]:
            self.assertTrue(adjustment["original_errors"])
            span = adjustment["source_span"]
            original = index[span["unit_id"]]["text"][span["start"]:span["end"]]
            self.assertTrue(original)
            self.assertIn(original, index[span["unit_id"]]["text"])

    def test_leaves_already_valid_evidence_scores_and_categories_unchanged(self):
        value = record()
        next_output, audit = normalized(value)
        self.assertEqual(next_output, output(value))
        self.assertEqual(audit["count"], 0)
        _, row = self.assert_scored(value)
        self.assertEqual(row["agent_assessment"], value)
        self.assertEqual(row["resume_evidence_strength"], .55)
        self.assertEqual(row["skill_gap"], .45)
        self.assertEqual(row["skill_gap_grade"], "C")
        self.assertEqual(row["priority"], .27)
        self.assertNotIn("original_agent_assessment", row)

    def test_offline_normalization_and_recalculation_never_invoke_agent(self):
        with patch("app.services.skill_gaps.transport.invoke", side_effect=AssertionError("No Agent allowed")) as invoke:
            result = report(record())
        invoke.assert_not_called()
        self.assertEqual(result["skills"][0]["resume_evidence_strength"], .55)

    def test_existing_omitted_prose_comma_restoration_still_works(self):
        sources = make_sources([OPERATION, "Used independent workers, and isolated queues.", CHECK])
        value = record()
        value["method"]["proof"]["quote"] = "Used independent workers and isolated queues."
        result, row = self.assert_scored(value, sources)
        self.assertEqual(row["agent_assessment"]["method"]["proof"]["quote"],
                         "Used independent workers, and isolated queues.")
        self.assertTrue(any(change["code"] == "omitted_comma_restored"
                            for change in result["response_processing"]["adjustments"]))

    def test_unknown_operation_id_does_not_supply_an_activity_anchor(self):
        value = record()
        value["operation_id"] = "e999"
        self.assert_unchanged_pending(value)

    def test_unknown_proof_id_is_not_replaced_by_global_text_search(self):
        value = record()
        value["method"]["proof"]["unit_id"] = "e999"
        self.assert_unchanged_pending(value)

    def test_does_not_take_an_exact_quote_from_another_activity(self):
        sources = make_sources([OPERATION, "Used local queues.", CHECK], [METHOD])
        value = record()
        self.assert_unchanged_pending(value, sources)

    def test_existing_cross_activity_reference_is_never_repaired(self):
        sources = make_sources(second=[METHOD])
        value = record()
        value["method"]["proof"] = {"unit_id": "e004", "quote": "used isolated worker processes."}
        self.assert_unchanged_pending(value, sources)

    def test_same_activity_duplicate_unit_matches_remain_pending(self):
        sources = make_sources([OPERATION, METHOD, CHECK, METHOD])
        value = record()
        value["method"]["proof"]["unit_id"] = "e001"
        self.assert_unchanged_pending(value, sources)

    def test_exact_sibling_and_in_unit_format_match_are_ambiguous(self):
        sources = make_sources([OPERATION, METHOD, CHECK, "used isolated worker processes."])
        value = record()
        value["method"]["proof"]["quote"] = "used isolated worker processes."
        self.assert_unchanged_pending(value, sources)

    def test_repeated_spans_within_one_unit_remain_pending(self):
        sources = make_sources([OPERATION, METHOD, "Checked expected requests; Checked expected requests."])
        value = record()
        value["validation"]["check"]["quote"] = "...Checked expected requests"
        self.assert_unchanged_pending(value, sources)

    def test_internal_ellipsis_is_not_reconstructed_into_missing_words(self):
        value = record()
        value["method"]["proof"]["quote"] = "Used...worker processes."
        self.assert_unchanged_pending(value)

    def test_internal_case_changes_are_not_treated_as_sentence_capitalization(self):
        sources = make_sources([OPERATION, "Used xBuffer for batching.", CHECK])
        value = record()
        value["method"]["proof"]["quote"] = "Used XBuffer for batching."
        self.assert_unchanged_pending(value, sources)

    def test_mixed_case_identifier_at_sentence_start_is_not_case_folded(self):
        sources = make_sources([OPERATION, "xBuffer processed queued jobs.", CHECK])
        value = record()
        value["method"]["proof"]["quote"] = "XBuffer processed queued jobs."
        self.assert_unchanged_pending(value, sources)

    def test_capitalization_inside_a_unit_is_not_treated_as_sentence_start(self):
        sources = make_sources([OPERATION, "The worker used isolated processes.", CHECK])
        value = record()
        value["method"]["proof"]["quote"] = "Used isolated processes."
        self.assert_unchanged_pending(value, sources)

    def test_case_repair_does_not_rewrite_backticks_or_underscored_identifiers(self):
        for original, changed in [("`Used` configured queues.", "`used` configured queues."),
                                  ("Worker_pool processed jobs.", "worker_pool processed jobs.")]:
            with self.subTest(original=original):
                sources = make_sources([OPERATION, original, CHECK])
                value = record()
                value["method"]["proof"]["quote"] = changed
                self.assert_unchanged_pending(value, sources)

    def test_case_repair_does_not_rewrite_assignments_or_string_literals(self):
        for original, changed in [("Batch = 16.", "batch = 16."),
                                  ("Batch -> process.", "batch -> process."),
                                  ('The label is "Active worker".', "active worker")]:
            with self.subTest(original=original):
                sources = make_sources([OPERATION, original, CHECK])
                value = record()
                value["method"]["proof"]["quote"] = changed
                self.assert_unchanged_pending(value, sources)

    def test_rebinding_requires_original_lexical_boundaries(self):
        for original, fragment in [("Measured 35ms latency.", "5ms"),
                                   ("Measured 3.5ms latency.", "5ms"),
                                   ("Used object.worker for dispatch.", "worker"),
                                   ("Used object.worker for dispatch.", "object"),
                                   ("The worker was unavailable.", "available")]:
            with self.subTest(fragment=fragment):
                sources = make_sources([OPERATION, original, CHECK])
                value = record()
                value["method"]["proof"] = {"unit_id": "e001", "quote": fragment}
                self.assert_unchanged_pending(value, sources)

    def test_punctuation_prefix_does_not_bypass_identifier_or_fraction_boundary(self):
        for original, fragment in [("Used library.v1.2 for dispatch.", ".2"),
                                   ("Recorded 1/3 during testing.", "/3")]:
            with self.subTest(fragment=fragment):
                sources = make_sources([OPERATION, original, CHECK])
                value = record()
                value["method"]["proof"] = {"unit_id": "e001", "quote": fragment}
                self.assert_unchanged_pending(value, sources)

    def test_punctuation_only_candidates_do_not_produce_alignment_audit(self):
        for original, fragment in [("Asked whether the worker was ready?", "?"),
                                   ("Waited...then processed requests.", "..."),
                                   ("Called worker().", "()")]:
            with self.subTest(fragment=fragment):
                sources = make_sources([OPERATION, original, CHECK])
                value = record()
                value["method"]["proof"] = {"unit_id": "e001", "quote": fragment}
                self.assert_unchanged_pending(value, sources)

    def test_format_repair_does_not_truncate_decimal_or_dotted_identifier(self):
        for original, fragment in [("Measured 3.5ms latency.", "...Measured 3"),
                                   ("Used release.v12.final.", "used release.v12")]:
            with self.subTest(fragment=fragment):
                sources = make_sources([OPERATION, original, CHECK])
                value = record()
                value["method"]["proof"]["quote"] = fragment
                self.assert_unchanged_pending(value, sources)

    def test_rebinding_does_not_split_signed_grouped_fractional_or_scientific_numbers(self):
        cases = [(".3ms", "3ms"), ("1,000", "000"), ("1,000", "1"),
                 ("+3", "3"), ("-.3", ".3"), ("1e-3", "1"), ("1/3", "3"),
                 ("\u22123", "3")]
        for literal, fragment in cases:
            for suffix in (" during testing.", "."):
                with self.subTest(literal=literal, fragment=fragment, suffix=suffix):
                    sources = make_sources([OPERATION, f"Recorded {literal}{suffix}", CHECK])
                    value = record()
                    value["method"]["proof"] = {"unit_id": "e001", "quote": fragment}
                    self.assert_unchanged_pending(value, sources)

    def test_full_numeric_literals_rebind_without_inventing_digits_or_signs(self):
        for literal in (".3ms", "1,000", "+3", "-.3", "1e-3", "1/3", "\u22123"):
            with self.subTest(literal=literal):
                sources = make_sources([OPERATION, f"Recorded {literal} during testing.", CHECK])
                value = record()
                value["method"]["proof"] = {"unit_id": "e001", "quote": literal}
                _, row = self.assert_scored(value, sources)
                self.assertEqual(row["agent_assessment"]["method"]["proof"],
                                 {"unit_id": "e002", "quote": literal})

    def test_complete_measured_value_and_prose_period_keep_original_scoring(self):
        for literal, unit_suffix in [(".3", "ms"), ("1,000", " requests")]:
            with self.subTest(literal=literal):
                check = "Checked response counts."
                finding = f"Observed {literal}{unit_suffix} during validation."
                sources = make_sources([OPERATION, METHOD, check + " " + finding])
                value = record()
                value["validation"] = {
                    "kind": "observed", "check": {"unit_id": "e003", "quote": check},
                    "finding": {"unit_id": "e003", "quote": finding},
                    "finding_type": "measured_value", "reported_value": literal,
                    "reference": None, "relation": "same_capability",
                }
                result, row = self.assert_scored(value, sources)
                self.assertEqual(row["resume_evidence_strength"], .65)
                self.assertEqual(row["agent_assessment"]["validation"]["reported_value"], literal)
                self.assertEqual(result["response_processing"]["count"], 0)

    def test_negation_is_not_inserted_removed_or_inferred(self):
        sources = make_sources([OPERATION, METHOD, "Did not verify expected requests."])
        value = record()
        value["validation"]["check"]["quote"] = "Did verify expected requests."
        self.assert_unchanged_pending(value, sources)

    def test_numeric_changes_and_numeric_commas_are_not_repaired(self):
        for source_quote, model_quote in [("Measured 35ms latency.", "Measured 30ms latency."),
                                           ("Measured 1,000 requests.", "Measured 1000 requests.")]:
            with self.subTest(model_quote=model_quote):
                sources = make_sources([OPERATION, METHOD, source_quote])
                value = record()
                value["validation"]["check"]["quote"] = model_quote
                self.assert_unchanged_pending(value, sources)

    def test_rolls_back_recoverable_quote_when_another_quote_is_invented(self):
        value = record()
        value["method"]["proof"]["quote"] = "used isolated worker processes."
        value["validation"]["check"]["quote"] = "Invented validation output."
        self.assert_unchanged_pending(value)

    def test_rolls_back_when_an_unrelated_record_shape_error_remains(self):
        value = record()
        value["method"]["proof"]["quote"] = "used isolated worker processes."
        value["method"]["kind"] = "invented_method_category"
        self.assert_unchanged_pending(value)

    def test_check_only_unexpected_results_are_not_removed_by_quote_alignment(self):
        for finding, reference in [(True, False), (False, True)]:
            with self.subTest(finding=finding, reference=reference):
                value = record()
                if finding:
                    value["validation"]["finding"] = deepcopy(value["validation"]["check"])
                    value["validation"]["finding_type"] = "observed_state"
                if reference:
                    value["validation"]["reference"] = {"unit_id": "e002", "quote": METHOD}
                self.assert_unchanged_pending(value)

    def test_existing_duplicate_check_only_reference_cleanup_is_preserved(self):
        value = record()
        value["validation"]["reference"] = deepcopy(value["validation"]["check"])
        result, row = self.assert_scored(value)
        self.assertIsNone(row["agent_assessment"]["validation"]["reference"])
        self.assertEqual([change["code"] for change in result["response_processing"]["adjustments"]],
                         ["duplicate_nonresult_reference_removed"])

    def test_new_alignment_audits_validate_against_proposed_storage_contract(self):
        path = Path(__file__).resolve().parents[2] / "docs/contracts/skill-gap-run-storage.schema.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator({"$ref": "#/$defs/ResponseProcessing", "$defs": contract["$defs"]})
        case = record()
        case["method"]["proof"]["quote"] = "used isolated worker processes."
        ellipsis = record()
        ellipsis["validation"]["check"]["quote"] = "...Checked expected requests"
        rebound = record()
        rebound["operation_id"] = "e002"
        duplicate = record()
        duplicate["validation"]["reference"] = deepcopy(duplicate["validation"]["check"])
        for value in (case, ellipsis, rebound, duplicate):
            with self.subTest(value=value):
                _, audit = normalized(value)
                self.assertGreater(audit["count"], 0)
                validator.validate(audit)
        _, audit = normalized(case)
        invalid = deepcopy(audit)
        invalid["adjustments"][0]["rules"] = ["infer_missing_evidence"]
        with self.assertRaises(ValidationError):
            validator.validate(invalid)

    def test_wrong_family_or_root_fields_do_not_trigger_alignment(self):
        for mutate in (lambda raw: raw["result"].update(job_family="data_analyst"),
                       lambda raw: raw.update(unrequested="value")):
            value = record()
            value["method"]["proof"]["quote"] = "used isolated worker processes."
            raw = output(value)
            mutate(raw)
            before = deepcopy(raw)
            next_output, audit = normalize_response(FAMILY, raw, CATALOG, make_sources())
            self.assertEqual(next_output, before)
            self.assertEqual(audit["count"], 0)


if __name__ == "__main__":
    unittest.main()
