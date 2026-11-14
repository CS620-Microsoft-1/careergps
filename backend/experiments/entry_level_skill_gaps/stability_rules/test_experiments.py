"""Meaningful protocol checks for the isolated fixed-source experiment."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import tempfile

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
from . import fixed_evidence as fixed
from app.services.skill_gaps.input import prepare
from app.services.skill_gaps.skill_groups import make_group_payloads
from . import rule_contract as rules
from . import prompt_variants
class RuleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = rules.load_cases()
        cls.payload = rules.build_payload(cls.cases)

    def answer(self):
        """Build a numeric/structural fixture, not a semantic model evaluation."""
        result = {"task": "assess_rule_cases", "results": []}
        for source, case in zip(self.cases, self.payload["cases"]):
            criteria = {}
            for cid in ("c1", "c2", "c3"):
                status = source["expected_criteria"][cid]
                ids = [] if status == "not_evidenced" else case["anchor_unit_ids"]
                if cid == "c3" and status == "supported" and len(case["activity"]["units"]) > 1:
                    ids = [case["activity"]["units"][-1]["id"]]
                criteria[cid] = {"status": status, "basis": "practice" if status in ("supported", "partial") else "unclear" if status == "uncertain" else "none", "unit_ids": ids}
            result["results"].append({"case_id": case["case_id"], "skill_id": case["skill_id"], "criteria": criteria})
        return result

    def test_no_expected_labels_descriptive_ids_or_split_in_payload(self):
        source = deepcopy(self.cases)
        source[0]["case_id"] = "definitely_supported_answer"
        source[0]["rationale"] = "unique_expected_answer_marker"
        text = json.dumps(rules.build_payload(source))
        for key in ("expected_criteria", "rationale", "split", "introduced_in", "synthetic"):
            self.assertNotIn('"' + key + '"', text)
        self.assertNotIn("definitely_supported_answer", text)
        self.assertNotIn("unique_expected_answer_marker", text)

    def test_versioned_case_counts_and_policy_arithmetic(self):
        self.assertEqual(len(rules.load_cases("v1")), 18)
        self.assertEqual(len(self.cases), 22)
        checked = rules.assess_output(self.answer(), self.payload)
        self.assertEqual(checked["schema_errors"], [])
        self.assertEqual([r["score"] for r in checked["rows"][:6]], [1.0, .5, 0.0, None, 0.0, .9])
        self.assertEqual([r["grade"] for r in checked["rows"][:6]], ["A", "C", "F", None, "F", "A"])
        self.assertFalse(checked["semantic_entailment_validated"])

    def test_unknown_source_stays_pending_without_repair(self):
        response = self.answer()
        response["results"][0]["criteria"]["c1"]["unit_ids"] = ["not_in_case"]
        before = deepcopy(response)
        row = rules.assess_output(response, self.payload)["rows"][0]
        self.assertIsNone(row["score"])
        self.assertIn("c1:invalid_source_ids", row["errors"])
        self.assertEqual(response, before)

    def test_bare_list_is_not_practice(self):
        response = self.answer()
        response["results"][2]["criteria"]["c1"] = {"status": "supported", "basis": "practice", "unit_ids": ["e001"]}
        row = rules.assess_output(response, self.payload)["rows"][2]
        self.assertIsNone(row["score"])
        self.assertIn("c1:ineligible_practice_reference", row["errors"])

    def test_partial_core_is_only_allowed_by_adapted_control(self):
        response = self.answer()
        response["results"][0]["criteria"]["c1"]["status"] = "partial"
        self.assertEqual(rules.assess_output(response, self.payload, "control")["rows"][0]["score"], .6)
        for mode in ("rules_v1", "rules_v1_1"):
            row = rules.assess_output(response, self.payload, mode)["rows"][0]
            self.assertIsNone(row["score"])
            self.assertIn("c1:partial_disabled", row["policy_violations"])

    def test_uncertain_core_remains_pending_and_suppresses_detail_credit(self):
        response = self.answer()
        response["results"][3]["criteria"]["c2"] = {"status": "uncertain", "basis": "unclear", "unit_ids": ["e001"]}
        row = rules.assess_output(response, self.payload)["rows"][3]
        self.assertIsNone(row["score"])
        self.assertIn("c2:detail_not_suppressed_for_unestablished_core", row["policy_violations"])

    def test_case_order_and_malformed_output_do_not_yield_scores(self):
        response = self.answer()
        response["results"][0], response["results"][1] = response["results"][1], response["results"][0]
        self.assertTrue(all(row["score"] is None for row in rules.assess_output(response, self.payload)["rows"]))
        for response in (None, {"results": [None]}, {"task": "assess_rule_cases", "results": "bad"}):
            self.assertTrue(all(row["score"] is None for row in rules.assess_output(response, self.payload)["rows"]))

    def test_malformed_reference_is_pending_without_crashing(self):
        response = self.answer()
        response["results"][0]["criteria"]["c1"]["unit_ids"] = [["invalid"]]
        self.assertIsNone(rules.assess_output(response, self.payload)["rows"][0]["score"])

    def test_duplicate_source_ids_and_foreign_anchors_rejected(self):
        source = deepcopy(self.cases[:1])
        source[0]["units"].append(deepcopy(source[0]["units"][0]))
        with self.assertRaises(ValueError):
            rules.build_payload(source)
        source = deepcopy(self.cases[:1])
        source[0]["anchor_unit_ids"] = ["absent"]
        with self.assertRaises(ValueError):
            rules.build_payload(source)

    def test_whole_synthetic_activity_context_preserved(self):
        activity = {"id": "a1", "context": {"title": "Synthetic project"}, "units": [
            {"id": "u1", "kind": "claim", "text": "I implemented a Python parser."},
            {"id": "u2", "kind": "claim", "text": "I planned future tests."}]}
        payload = rules.build_payload([{"skill_id": "python", "activity": activity, "anchor_unit_ids": ["u1"]}])
        self.assertEqual(payload["cases"][0]["activity"], activity)
        self.assertIsNot(payload["cases"][0]["activity"], activity)

    def test_offline_cli_uses_real_catalog_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix=".test-") as folder:
            self.assertEqual(Path(folder).resolve().parent, HERE.resolve())
            request = Path(folder) / "request.json"
            response = Path(folder) / "response.json"
            report = Path(folder) / "report.json"
            self.assertEqual(rules.main(["prepare", "--output", str(request)]), 0)
            self.assertEqual(rules.read(request), self.payload)
            rules.save_new(response, self.answer())
            self.assertEqual(rules.main(["score", "--input", str(request), "--response", str(response), "--output", str(report)]), 0)
            self.assertEqual(rules.read(report)["rows"][0]["score"], 1.0)
            with self.assertRaises(FileExistsError):
                rules.main(["prepare", "--output", str(request)])

    def test_clarification_preserves_all_other_rule_text(self):
        before = prompt_variants.build_instructions("rules_v1")
        after = prompt_variants.build_instructions("rules_v1_1")
        self.assertEqual(after, before.replace("entry-level-three-skill-rule.v1\n", "entry-level-three-skill-rule.v1.1\n") + "\n" + prompt_variants.CLARIFICATION)
        for group in ("foundation", "lifecycle", "systems"):
            self.assertIn("focused omission check", prompt_variants.build_instructions("prompt_stability", group))
            self.assertEqual(prompt_variants.build_instructions("fixed_evidence", group), fixed.build_instructions(group))


class FixedPacketTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((BACKEND/'app/services/skill_gaps/data/core_catalog.json').read_text(encoding='utf-8'))
        self.criteria = json.loads((HERE.parent/'entry_agents/criteria.json').read_text(encoding='utf-8'))
        self.full = prepare('ai_engineer', {'projects': [
            {'name': 'Selected', 'content': ['I implemented a Python parser.', 'I tested malformed records.']},
            {'name': 'Other', 'content': ['I implemented an unrelated Java service.']},
            {'name': 'Excluded', 'content': ['I operated a separate database.']}],
            'technical_skills': ['Python']}, 'fixed-test', self.catalog)
        self.base = make_group_payloads(self.full)['foundation']
        self.a, self.b, self.c = self.full['resume_sources'][:3]
        ids = self.base['evidence_scope']['assigned_skill_ids']
        self.packet = {'version': 'test', 'resume_sources_sha256': fixed._sha(self.full['resume_sources']),
            'skills': {skill: {'activity_id': self.a['id'], 'unit_ids': [u['id'] for u in self.a['units']],
                'anchor_unit_ids': [self.a['units'][0]['id']]} for skill in ids}}
        self.packet['skills']['sql'] = {'activity_id': self.b['id'],
            'unit_ids': [u['id'] for u in self.b['units']], 'anchor_unit_ids': [self.b['units'][0]['id']]}
        self.payload = fixed.build_payload(self.base, self.criteria, self.packet)
        self.output = {'task': fixed.compact.TASK, 'proofs': [], 'result': {'job_family':'ai_engineer'}}
        for skill in ids:
            self.output['result'][skill] = {'criteria': [{'criterion_id': c['id'], 'status':'not_evidenced',
                'basis':'none','proof_ids':[]} for c in self.criteria['families']['ai_engineer'][skill]['criteria']]}

    def positive_python(self, unit=None):
        unit = unit or self.a['units'][0]
        self.output['proofs'] = [{'proof_id':'p1','unit_id':unit['id'],'quote':unit['text']}]
        for c in self.output['result']['python']['criteria']:
            c.update(status='supported', basis='practice', proof_ids=['p1'])

    def test_lossless_activity_union_and_cards(self):
        self.assertEqual([self.a, self.b], self.payload['resume_sources'])
        self.assertEqual(self.base['core_skills'], self.payload['core_skills'])
        self.assertEqual([self.a['id'],self.b['id']], self.payload['evidence_scope']['activity_ids'])
        expected = fixed.compact.build_payload(self.base, self.criteria)
        self.assertEqual(expected['entry_level_criteria'], self.payload['entry_level_criteria'])
        self.assertEqual(fixed.compact.CONTRACT_VERSION, self.payload['evidence_contract'])
        self.assertEqual(fixed.compact.build_format(self.catalog,'foundation',self.criteria),
                         fixed.build_format(self.catalog,'foundation',self.criteria))

    def test_no_expectations_or_notes_leak(self):
        self.packet['expected_grade'] = 'A'
        self.packet['skills']['python']['status'] = 'supported'
        self.packet['skills']['python']['notes'] = 'This is a reviewer conclusion'
        payload = fixed.build_payload(self.base, self.criteria, self.packet)
        self.assertEqual(set(fixed.PACKET_FIELDS), set(payload['fixed_evidence_packets']['skills']['python']))
        self.assertNotIn('reviewer conclusion', json.dumps(payload))

    def test_prebuilt_compact_payload_api_is_equivalent_and_not_mutated(self):
        base = fixed.compact.build_payload(self.base, self.criteria)
        before = deepcopy(base)
        self.assertEqual(self.payload, fixed.build_payload(base, self.packet))
        self.assertEqual(before, base)

    def test_fingerprint_drift_rejected(self):
        self.packet['resume_sources_sha256'] = 'changed'
        with self.assertRaises(ValueError): fixed.build_payload(self.base,self.criteria,self.packet)

    def test_partial_activity_or_foreign_anchor_rejected(self):
        bad = deepcopy(self.packet)
        bad['skills']['python']['unit_ids'].pop()
        with self.assertRaises(ValueError): fixed.build_payload(self.base,self.criteria,bad)
        bad = deepcopy(self.packet)
        bad['skills']['python']['anchor_unit_ids'] = [self.b['units'][0]['id']]
        with self.assertRaises(ValueError): fixed.build_payload(self.base,self.criteria,bad)

    def test_compliant_output_uses_original_score(self):
        self.positive_python()
        original = fixed.compact.assess_output(self.output,self.payload,self.catalog,self.criteria)
        scored = fixed.assess_output(self.output,self.payload,self.catalog,self.criteria)
        self.assertEqual(original, scored)
        self.assertEqual(1.0,next(r for r in scored['skills'] if r['skill_id']=='python')['entry_level_score'])
        self.assertTrue(fixed.audit_compliance(self.output,self.payload)['compliant'])

    def test_cross_skill_pool_escape_is_separate_from_score(self):
        self.positive_python(self.b['units'][0])
        before = deepcopy(self.output)
        scored = fixed.assess_output(self.output,self.payload,self.catalog,self.criteria)
        self.assertEqual(1.0,next(r for r in scored['skills'] if r['skill_id']=='python')['entry_level_score'])
        compliance = fixed.audit_compliance(self.output,self.payload)
        self.assertFalse(compliance['compliant'])
        self.assertEqual(['python'],compliance['violating_skill_ids'])
        self.assertIn('c1:proof_outside_skill_packet', next(r for r in compliance['skills'] if r['skill_id']=='python')['errors'])
        self.assertEqual(before,self.output)

    def test_missing_anchor_within_same_activity_fails_protocol(self):
        self.positive_python(self.a['units'][1])
        compliance = fixed.audit_compliance(self.output,self.payload)
        self.assertIn('c1:core_did_not_cite_fixed_anchor',next(r for r in compliance['skills'] if r['skill_id']=='python')['errors'])

    def test_method_and_check_may_use_other_units_of_fixed_activity(self):
        self.positive_python()
        unit=self.a['units'][1]
        self.output['proofs'].append({'proof_id':'p2','unit_id':unit['id'],'quote':unit['text']})
        self.output['result']['python']['criteria'][2]['proof_ids']=['p2']
        self.assertTrue(fixed.audit_compliance(self.output,self.payload)['compliant'])

    def test_uncertain_requires_anchor_but_absence_does_not(self):
        self.assertTrue(fixed.audit_compliance(self.output,self.payload)['compliant'])
        c1=self.output['result']['python']['criteria'][0]
        c1.update(status='uncertain',basis='unclear')
        self.assertFalse(fixed.audit_compliance(self.output,self.payload)['compliant'])
        unit=self.a['units'][0]
        self.output['proofs']=[{'proof_id':'p1','unit_id':unit['id'],'quote':unit['text']}]
        c1['proof_ids']=['p1']
        self.assertTrue(fixed.audit_compliance(self.output,self.payload)['compliant'])

    def test_duplicate_and_unknown_proof_ids_fail_protocol(self):
        self.positive_python()
        self.output['proofs'].append(deepcopy(self.output['proofs'][0]))
        self.assertFalse(fixed.audit_compliance(self.output,self.payload)['compliant'])
        self.output['proofs']=[]
        self.assertFalse(fixed.audit_compliance(self.output,self.payload)['compliant'])

    def test_malformed_unit_reference_is_reported_without_crashing(self):
        self.positive_python()
        self.output['proofs'][0]['unit_id'] = ['invalid']
        result = fixed.audit_compliance(self.output,self.payload)
        self.assertFalse(result['compliant'])
        self.assertEqual(result['violations'], result['errors'])

    def test_original_judgment_and_output_sections_unchanged(self):
        for group in ('foundation','lifecycle','systems'):
            old=fixed.compact.build_instructions(group)
            new=fixed.build_instructions(group)
            self.assertEqual(old.split('JUDGMENTS\n',1)[1],new.split('JUDGMENTS\n',1)[1])
            self.assertLess(len(new)-len(old),1100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
