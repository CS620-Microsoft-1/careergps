import copy
import json
import unittest

from scripts.test_skill_gap_structured_local import (
    JobsOutput, ResumeOutput, calculate_final, catalog, demand_from,
    generate_postings, score_matches, validate_final, validate_jobs, FinalOutput,
    decode_task_response,
)


class StructuredLocalTests(unittest.TestCase):
    def setUp(self):
        self.postings, self.expected = generate_postings()
        self.definitions = catalog()

    def extraction(self, postings=None):
        outputs = []
        for posting in postings or self.postings:
            criteria = []
            qualifications = posting["parsed_job_description"]["qualifications"]
            for index, (key, level) in enumerate(self.expected[posting["posting_id"]].items()):
                definition = next(c for c in self.definitions if c["criterion_id"] == key)
                criteria.append({**{k: v for k, v in definition.items() if k not in {"criterion_id", "scored"}},
                                 "level": level, "evidence": [{"source_path": f"/qualifications/{index}/evidence/0/quote",
                                 "source_field": "description_text", "quote": qualifications[index]["value"]}]})
            outputs.append({"posting_id": posting["posting_id"], "criteria": criteria,
                            "responsibilities": [], "job_conditions": []})
        return JobsOutput.model_validate({"postings": outputs})

    def matches(self, definition, citations, status="supported", options=None):
        return ResumeOutput.model_validate({"criteria": [{"criterion_id": definition["criterion_id"],
            "status": status, "matched_options": options or [], "evidence": citations, "explanation": "Test"}],
            "conditions_to_confirm": []})

    def test_twenty_unique_synthetic_sources_match_new_shape(self):
        self.assertEqual(20, len(self.postings))
        self.assertEqual(20, len({p["posting_id"] for p in self.postings}))
        self.assertEqual(10, len({p["original_source"]["company_name"] for p in self.postings}))
        expected_fields = {"job_title", "company_name", "job_family", "seniority", "department", "locations",
                           "role_overview", "responsibilities", "qualifications", "job_conditions", "compensation",
                           "benefits", "other_relevant_information"}
        self.assertTrue(all(set(p["parsed_job_description"]) == expected_fields for p in self.postings))

    def test_agent_envelope_extracts_correct_task_data(self):
        raw = json.dumps({"response": {"task": "extract_job_requirements", "data": {"postings": []}}})
        result = decode_task_response(raw, "extract_job_requirements", JobsOutput, wrapped=True)
        self.assertEqual([], result.postings)

    def test_agent_envelope_resume_branch(self):
        raw = json.dumps({"response": {"task": "extract_resume_evidence", "data": {"criteria": [], "conditions_to_confirm": []}}})
        result = decode_task_response(raw, "extract_resume_evidence", ResumeOutput, wrapped=True)
        self.assertEqual([], result.criteria)

    def test_agent_envelope_rejects_wrong_task_and_missing_wrapper(self):
        raw = json.dumps({"response": {"task": "extract_job_requirements", "data": {"postings": []}}})
        with self.assertRaisesRegex(ValueError, "task mismatch"):
            decode_task_response(raw, "extract_resume_evidence", ResumeOutput, wrapped=True)
        with self.assertRaises(ValueError):
            decode_task_response('{"postings":[]}', "extract_job_requirements", JobsOutput, wrapped=True)

    def test_agent_envelope_rejects_extra_fields(self):
        raw = json.dumps({"response": {"task": "extract_job_requirements", "data": {"postings": []}}, "debug": "extra"})
        with self.assertRaises(ValueError):
            decode_task_response(raw, "extract_job_requirements", JobsOutput, wrapped=True)

    def test_unwrapped_legacy_decoding_still_supported(self):
        result = decode_task_response('{"postings":[]}', "extract_job_requirements", JobsOutput, wrapped=False)
        self.assertEqual([], result.postings)

    def test_extraction_grounding_and_demand(self):
        records = validate_jobs(self.extraction(), self.postings, self.definitions)
        self.assertEqual(self.expected, records)
        demand = demand_from(records, self.definitions)
        self.assertEqual(20, demand["programming"]["required_postings"])
        self.assertEqual(10, demand["ai_tools"]["preferred_only_postings"])
        self.assertEqual(0, demand["ai_tools"]["required_postings"])
        self.assertEqual(.5, demand["ai_tools"]["combined_ratio"])
        self.assertEqual(8, demand["web_ui"]["required_postings"])

    def test_duplicate_skill_mentions_count_once(self):
        extraction = self.extraction()
        extraction.postings[0].criteria.append(extraction.postings[0].criteria[0].model_copy())
        records = validate_jobs(extraction, self.postings, self.definitions)
        self.assertEqual(20, demand_from(records, self.definitions)["programming"]["required_postings"])

    def test_rejects_changed_or_logic(self):
        result = self.extraction()
        result.postings[0].criteria[0].requirement_logic = "all_of"
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            validate_jobs(result, self.postings, self.definitions)

    def test_rejects_wrong_requirement_level(self):
        result = self.extraction()
        result.postings[0].criteria[0].level = "preferred"
        with self.assertRaisesRegex(ValueError, "same level"):
            validate_jobs(result, self.postings, self.definitions)

    def test_rejects_fabricated_source_quote(self):
        result = self.extraction()
        result.postings[0].criteria[0].evidence[0].quote = "Invented"
        with self.assertRaisesRegex(ValueError, "quotation"):
            validate_jobs(result, self.postings, self.definitions)

    def test_jd_wrong_wrapper_path_has_actionable_feedback(self):
        result = self.extraction()
        result.postings[0].criteria[0].evidence[0].source_path = "/parsed_job_description/description_text"
        with self.assertRaisesRegex(ValueError, "relative to parsed_job_description"):
            validate_jobs(result, self.postings, self.definitions)

    def test_checks_original_not_only_upstream_json(self):
        result = self.extraction()
        postings = copy.deepcopy(self.postings)
        postings[0]["original_source"]["description_text"] = "Unrelated original text"
        with self.assertRaisesRegex(ValueError, "independently retained"):
            validate_jobs(result, postings, self.definitions)

    def test_one_programming_option_suffices(self):
        definition = self.definitions[0]
        resume = {"projects": [{"content": ["Implemented Python commands."]}]}
        result = self.matches(definition, [{"path": "/projects/0/content/0", "quote": "Implemented Python commands.", "kind": "applied"}], options=["Python"])
        self.assertEqual(.6, score_matches(result, resume, [definition])["programming"])

    def test_missing_evidence_zero_not_ability_judgment(self):
        definition = self.definitions[0]
        result = self.matches(definition, [], "not_evidenced")
        self.assertEqual(0, score_matches(result, {}, [definition])["programming"])

    def test_nontechnical_scores_remain_null(self):
        definition = next(c for c in self.definitions if c["criterion_id"] == "collaboration")
        self.assertIsNone(score_matches(self.matches(definition, [], "not_evidenced"), {}, [definition])["collaboration"])

    def test_conceptual_exposure_is_partial_not_satisfied_platform_option(self):
        definition = next(c for c in self.definitions if c["criterion_id"] == "cloud")
        text = "Introductory Cloud Architecture Course Certificate"
        result = self.matches(definition, [{"path": "/certifications/0/name", "quote": text, "kind": "listed"}], "partial")
        source = {"certifications": [{"name": text}]}
        self.assertEqual(.25, score_matches(result, source, [definition])["cloud"])
        result.criteria[0].status = "supported"
        with self.assertRaisesRegex(ValueError, "Full any-of"):
            score_matches(result, source, [definition])

    def test_duplicate_quotes_do_not_inflate_independent_contexts(self):
        definition = self.definitions[0]
        text = "Wrote and ran Python unit tests."
        resume = {"projects": [{"content": [text]}, {"content": [text]}]}
        citations = [{"path": f"/projects/{i}/content/0", "quote": text, "kind": "validated"} for i in range(2)]
        result = self.matches(definition, citations, options=["Python"])
        self.assertEqual(.8, score_matches(result, resume, [definition])["programming"])

    def test_two_independent_validated_contexts_score_one(self):
        definition = self.definitions[0]
        texts = ["Wrote and ran Python unit tests.", "Verified Python output hashes against fixed fixtures."]
        resume = {"projects": [{"content": [text]} for text in texts]}
        citations = [{"path": f"/projects/{i}/content/0", "quote": text, "kind": "validated"} for i, text in enumerate(texts)]
        result = self.matches(definition, citations, options=["Python"])
        self.assertEqual(1, score_matches(result, resume, [definition])["programming"])

    def test_rejects_string_index_path(self):
        definition = self.definitions[0]
        result = self.matches(definition, [{"path": "/other/0/content/0", "quote": "P", "kind": "listed"}], options=["Python"])
        with self.assertRaises(ValueError):
            score_matches(result, {"other": [{"content": "Python"}]}, [definition])

    def test_partial_cap_and_final_numeric_integrity(self):
        definition = self.definitions[0]
        text = "Wrote and ran Python unit tests."
        result = self.matches(definition, [{"path": "/projects/0/content/0", "quote": text, "kind": "validated"}], "partial", ["Python"])
        scores = score_matches(result, {"projects": [{"content": [text]}]}, [definition])
        self.assertEqual(.6, scores["programming"])
        demands = demand_from(self.expected, [definition])
        calculated = calculate_final([definition], demands, result, scores,
                                     {"sample_size": 20, "company_count": 10, "low_confidence": True}, [])
        self.assertEqual(.4, calculated["criteria"][0]["gap"]["score"])
        final = copy.deepcopy(calculated)
        final["summary"] = "Synthetic evidence comparison."
        final["criteria"][0]["gap"]["reason"] = "Partial evidence."
        final["criteria"][0]["recommended_action"] = "Add a tested demonstration."
        final["criteria"][0]["completion_evidence"] = "Reproducible tests."
        validate_final(FinalOutput.model_validate(final), calculated)
        final["criteria"][0]["gap"]["score"] = .1
        with self.assertRaisesRegex(ValueError, "immutable"):
            validate_final(FinalOutput.model_validate(final), calculated)


if __name__ == "__main__":
    unittest.main()
