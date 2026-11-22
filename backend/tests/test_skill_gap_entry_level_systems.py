"""Exercise Systems fact gates through the production assessment entry point."""
from copy import deepcopy
import unittest

from tests.test_skill_gap_entry_level_rules import (
    add_proof, assess_case, make_case, set_criterion, skill_row,
)


LLM = [
    "I used an LLM to generate answers for the support assistant.",
    "I sent the user's question and a response template in the prompt.",
    "I checked the model-generated answers against reference answers for factual agreement.",
]
RAG = [
    "I retrieved documents and passed the retrieved context to the LLM to generate answers.",
    "I retrieved the top three documents by cosine similarity and inserted them into the prompt.",
    "I checked generated answers against the retrieved documents for factual agreement.",
]
VECTOR = [
    "I implemented and ran vector similarity search to retrieve documents for user questions.",
    "I used cosine similarity over document embeddings to return the top three matches.",
    "I checked the returned documents against expected relevant documents for five queries.",
]


def systems_case(lines, *, permissions=None):
    return make_case("ai_engineer", "systems", projects=[{"name": "Assistant", "content": lines}],
                     permissions=permissions)


def children(output, lines):
    return {cid: {"status": "supported", "basis": "practice",
                  "proof_ids": [add_proof(output, f"e00{i}", lines[i - 1])]}
            for i, cid in ((2, "c2"), (3, "c3"))}


def full_llm(case):
    output = case[2]
    for i in range(2):
        set_criterion(output, "llm", f"c{i + 1}", "supported", uid=f"e00{i + 1}", quote=LLM[i])
    output["result"]["llm"]["check_facts"] = {
        "event": "performed", "workload_link": "same", "action": "checked",
        "checked_output": "model-generated answers", "detail": "against reference answers for factual agreement",
        "proof_ids": [add_proof(output, "e003", LLM[2])],
    }


def full_rag(case):
    output = case[2]
    output["result"]["rag"] = {
        "core_facts": {"personal_retrieval": "performed", "model_generation": "explicit",
                       "retrieval_use": "generation_context", "workload_link": "same",
                       "proof_ids": [add_proof(output, "e001", RAG[0])]},
        "children": children(output, RAG),
    }


def full_vector(case):
    output = case[2]
    output["result"]["vector_retrieval"] = {
        "core_facts": {"claim_kind": "operation", "execution": "performed", "method": "similarity_search",
                       "ownership": "personal", "workload_link": "same",
                       "proof_ids": [add_proof(output, "e001", VECTOR[0])]},
        "children": children(output, VECTOR),
    }


class EntryLevelSystemsTests(unittest.TestCase):
    def test_llm_performed_identified_check_scores_full_credit(self):
        case = systems_case(LLM)
        full_llm(case)
        original = deepcopy(case[2])
        assessment = assess_case(case)
        row = skill_row(assessment, "llm")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], 1)
        self.assertEqual(assessment["fact_audits"]["llm"]["mapped_status"], "supported")
        self.assertEqual(case[2], original)

    def test_llm_performed_check_without_detail_gets_partial_check_credit(self):
        case = systems_case(LLM[:2] + ["I checked the model-generated answers."])
        full_llm(case)
        facts = case[2]["result"]["llm"]["check_facts"]
        facts["detail"] = ""
        case[2]["proofs"][-1]["quote"] = "I checked the model-generated answers."
        row = skill_row(assess_case(case), "llm")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], .9)

    def test_llm_planned_check_does_not_receive_check_credit(self):
        planned = "I planned to check the model-generated answers against reference answers."
        case = systems_case(LLM[:2] + [planned])
        full_llm(case)
        case[2]["proofs"][-1]["quote"] = planned
        case[2]["result"]["llm"]["check_facts"].update(
            event="planned", workload_link="not_applicable", action="", checked_output="", detail="")
        row = skill_row(assess_case(case), "llm")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], .8)

    def test_llm_unidentified_checked_output_is_pending(self):
        case = systems_case(LLM[:2] + ["I checked it."])
        full_llm(case)
        case[2]["proofs"][-1]["quote"] = "I checked it."
        case[2]["result"]["llm"]["check_facts"].update(checked_output="", detail="")
        assessment = assess_case(case)
        self.assertIsNone(skill_row(assessment, "llm")["entry_level_score"])
        self.assertEqual(assessment["semantic_pending_reasons"]["llm"], ["checked_output_unidentified"])

    def test_llm_check_action_must_exist_in_its_exact_quote(self):
        case = systems_case(LLM)
        full_llm(case)
        case[2]["result"]["llm"]["check_facts"]["action"] = "benchmarked"
        row = skill_row(assess_case(case), "llm")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("fact:action_object_not_in_same_exact_quote", row["errors"])

    def test_llm_fact_quote_must_be_permitted_for_c3(self):
        case = systems_case(LLM, permissions={"llm": {"c3": []}})
        full_llm(case)
        assessment = assess_case(case)
        row = skill_row(assessment, "llm")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("fact:fact_proof_outside_fixed_criterion_candidates", row["errors"])
        self.assertEqual(assessment["citation_review"]["group_blocking_errors"], [])

    def test_rag_full_chain_can_receive_method_and_check_credit(self):
        case = systems_case(RAG)
        full_rag(case)
        row = skill_row(assess_case(case), "rag")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], 1)

    def test_rag_unresolved_generation_link_blocks_child_credit(self):
        case = systems_case(["I retrieved documents and handed the results to another component."])
        output = case[2]
        output["result"]["rag"]["core_facts"].update(
            personal_retrieval="performed", model_generation="not_stated",
            retrieval_use="unspecified_output", workload_link="unclear",
            proof_ids=[add_proof(output, "e001", "I retrieved documents and handed the results to another component.")])
        row = skill_row(assess_case(case), "rag")
        self.assertIsNone(row["entry_level_score"])
        self.assertEqual([a["status"] for a in row["criterion_audits"][1:]],
                         ["blocked_by_unresolved_core", "blocked_by_unresolved_core"])

    def test_rag_absent_core_cannot_receive_children(self):
        case = systems_case(RAG)
        case[2]["result"]["rag"]["children"] = children(case[2], RAG)
        row = skill_row(assess_case(case), "rag")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("rag_conditional_child_shape_invalid", row["errors"])

    def test_vector_performed_personal_operation_can_receive_full_credit(self):
        case = systems_case(VECTOR)
        full_vector(case)
        row = skill_row(assess_case(case), "vector_retrieval")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], 1)

    def test_vector_unclear_ownership_is_pending_and_blocks_children(self):
        text = "Our team ran vector similarity search for user questions."
        case = systems_case([text])
        case[2]["result"]["vector_retrieval"]["core_facts"].update(
            claim_kind="operation", execution="performed", method="similarity_search",
            ownership="unclear", workload_link="same", proof_ids=[add_proof(case[2], "e001", text)])
        row = skill_row(assess_case(case), "vector_retrieval")
        self.assertIsNone(row["entry_level_score"])
        self.assertEqual([a["status"] for a in row["criterion_audits"][1:]],
                         ["blocked_by_unresolved_core", "blocked_by_unresolved_core"])

    def test_bounded_vector_design_gets_only_partial_core(self):
        text = ("I designed retrieval of manuals from user queries using cosine similarity over embeddings; "
                "the design returns three manuals, but I did not execute retrieval.")
        case = systems_case([text])
        pid = add_proof(case[2], "e001", text)
        case[2]["result"]["vector_retrieval"]["core_facts"].update(
            claim_kind="design", execution="explicitly_not_performed", method="similarity_search",
            ownership="personal", workload_link="same", proof_ids=[pid])
        case[2]["partial_core"]["vector_retrieval"] = [pid]
        row = skill_row(assess_case(case), "vector_retrieval")
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["entry_level_score"], .25)
        self.assertTrue(row["partial_core_applied"])
        self.assertEqual([a["status"] for a in row["criterion_audits"][1:]],
                         ["blocked_by_partial_core", "blocked_by_partial_core"])

    def test_bounded_vector_design_cannot_add_method_and_check_credit(self):
        text = "I designed vector similarity search but did not execute it."
        case = systems_case([text, VECTOR[1], VECTOR[2]])
        pid = add_proof(case[2], "e001", text)
        case[2]["result"]["vector_retrieval"]["core_facts"].update(
            claim_kind="design", execution="explicitly_not_performed", method="similarity_search",
            ownership="personal", workload_link="same", proof_ids=[pid])
        case[2]["result"]["vector_retrieval"]["children"] = children(case[2], VECTOR)
        case[2]["partial_core"]["vector_retrieval"] = [pid]
        row = skill_row(assess_case(case), "vector_retrieval")
        self.assertIsNone(row["entry_level_score"])
        self.assertIn("vector_conditional_child_shape_invalid", row["errors"])


if __name__ == "__main__":
    unittest.main()
