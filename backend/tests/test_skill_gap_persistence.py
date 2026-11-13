"""Skill Gap run → database rows (app/services/skill_gaps/persistence.py). Synthetic data, no database."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker

from app.models.skill_gap import SkillGapResult, SkillGapRunBranch, SkillGapRunRecord
from app.services.skill_gaps.match import summarize_match
from app.services.skill_gaps.persistence import (
    STORAGE_SCHEMA_VERSION, branch_row, canonical_sha256, completion_fields, evidence_items,
    queued_run_row, result_rows, run_uuid,
)
from app.services.skill_gaps.storage import load
from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, absent_response, group_manager, reviewed_resume
from tests.test_skill_gap_run_ownership import wait_for

CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"
RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
# Columns the store fills itself (server defaults) rather than the mapping.
_SERVER_FILLED = {"created_at", "updated_at"}


def contract():
    return json.loads((CONTRACTS / "skill-gap-run-storage.schema.json").read_text(encoding="utf-8"))


def v3_example():
    return json.loads((CONTRACTS / "skill-gap-run-storage-v3.example.json").read_text(encoding="utf-8"))


def as_contract_row(row: dict) -> dict:
    """A skill_gap_results row in the contract's shape (its run fields live on the run record).

    original_agent_assessment is optional in the contract; the database column is NULL when Python
    left the Agent's record unchanged.
    """
    value = {key: value for key, value in row.items() if key not in ("run_id", "user_id", "job_family")}
    if value["original_agent_assessment"] is None:
        del value["original_agent_assessment"]
    return value


def model_columns(model) -> set[str]:
    return set(model.__table__.columns.keys())


class ResultRowsTests(unittest.TestCase):
    def setUp(self):
        self.example = v3_example()
        self.report = self.example["report"]
        self.rows = result_rows(self.report, self.example["extraction_audit"], run_id=RUN_ID,
                                user_id=UUID(self.example["user_id"]), job_family=self.example["job_family"])

    def test_rows_match_the_v3_contract_example(self):
        self.assertEqual(self.example["results"], [as_contract_row(row) for row in self.rows])

    def test_rows_validate_against_the_contract(self):
        record = deepcopy(self.example)
        record["results"] = [as_contract_row(row) for row in self.rows]
        Draft202012Validator(contract(), format_checker=FormatChecker()).validate(record)

    def test_rows_fill_every_result_column(self):
        for row in self.rows:
            self.assertEqual(model_columns(SkillGapResult) - _SERVER_FILLED, set(row))

    def test_one_row_per_skill_in_catalog_order_owned_by_the_run(self):
        self.assertEqual([row["skill_id"] for row in self.report["skills"]], [row["skill_id"] for row in self.rows])
        self.assertEqual(list(range(len(self.rows))), [row["position"] for row in self.rows])
        self.assertEqual({(RUN_ID, UUID(self.example["user_id"]), "software_engineer")},
                         {(row["run_id"], row["user_id"], row["job_family"]) for row in self.rows})

    def test_ranks_follow_the_priority_order_and_skip_unscored_skills(self):
        ranked = sorted((row for row in self.rows if row["priority_rank"]), key=lambda row: row["priority_rank"])
        self.assertEqual(self.report["priority_order"], [row["skill_id"] for row in ranked])
        for row in self.rows:
            if row["calculation_state"] == "needs_confirmation":
                self.assertIsNone(row["priority_rank"])

    def test_each_row_records_the_group_that_decided_it(self):
        audit = self.example["extraction_audit"]["skills"]
        for row in self.rows:
            self.assertEqual(audit[row["skill_id"]]["selected_branch"], row["branch"])
            self.assertEqual(audit[row["skill_id"]], row["merge_audit"])

    def test_rows_do_not_share_objects_with_the_report(self):
        self.rows[0]["agent_assessment"]["kind"] = "changed"
        self.assertNotEqual("changed", self.report["skills"][0]["agent_assessment"]["kind"])

    def test_a_single_agent_report_has_no_branch_or_merge_audit(self):
        rows = result_rows(self.report, None, run_id=RUN_ID, user_id=USER_ID, job_family="software_engineer")
        self.assertEqual({None}, {row["branch"] for row in rows})
        self.assertEqual({None}, {row["merge_audit"] for row in rows})

    def test_a_report_for_another_role_is_refused(self):
        with self.assertRaises(ValueError):
            result_rows(self.report, None, run_id=RUN_ID, user_id=USER_ID, job_family="data_analyst")

    def test_a_report_listing_a_skill_twice_is_refused(self):
        report = deepcopy(self.report)
        report["skills"].append(deepcopy(report["skills"][0]))
        with self.assertRaises(ValueError):
            result_rows(report, None, run_id=RUN_ID, user_id=USER_ID, job_family="software_engineer")


class EvidenceItemsTests(unittest.TestCase):
    def setUp(self):
        example = v3_example()
        self.sources = example["report"]["source_index"]
        self.skills = {row["skill_id"]: row for row in example["report"]["skills"]}

    def test_practice_quotes_are_the_checked_spans(self):
        items = evidence_items(self.skills["programming"], self.sources)
        self.assertEqual(["capability", "method", "check"], [item["role"] for item in items])
        for item in items:
            self.assertEqual(self.sources[item["unit_id"]]["text"][item["start"]:item["end"]], item["quote"])
        self.assertEqual("Implemented Python API endpoints", items[0]["quote"])
        self.assertEqual(("a002", "/projects/0/content/0"), (items[0]["activity_id"], items[0]["source_path"]))

    def test_knowledge_quotes_its_whole_unit(self):
        [item] = evidence_items(self.skills["algorithms"], self.sources)
        self.assertEqual("knowledge", item["role"])
        self.assertEqual(self.sources["e001"]["text"], item["quote"])
        self.assertEqual((0, len(item["quote"])), (item["start"], item["end"]))

    def test_absent_and_unit_less_uncertain_records_have_no_evidence(self):
        uncertain = self.skills["distributed_systems"]
        self.assertIsNone(uncertain["agent_assessment"]["evidence_id"])
        self.assertEqual([], evidence_items(uncertain, self.sources))
        absent = next(row for row in self.skills.values() if row["agent_assessment"]["kind"] == "absent")
        self.assertEqual([], evidence_items(absent, self.sources))

    def test_unknown_spans_and_missing_units_are_refused(self):
        for mutate in (lambda row: row["local_reference_check"]["proof_spans"][0].update(field="/result/x/summary"),
                       lambda row: row["local_reference_check"]["proof_spans"][0].update(unit_id="e999"),
                       lambda row: row["local_reference_check"]["proof_spans"][0].update(start=5, end=5)):
            row = deepcopy(self.skills["programming"])
            mutate(row)
            with self.assertRaises(ValueError):
                evidence_items(row, self.sources)


class RunAndBranchRowTests(unittest.TestCase):
    def state(self, **changes):
        value = {"id": uuid4().hex, "user_id": str(USER_ID), "resume_id": str(RESUME_ID),
                 "job_family": "software_engineer", "resume_hash": "a" * 64, "status": "queued", "phase": "queued",
                 "created_at": "2026-11-13T12:00:00+00:00", "confirmed_at": CONFIRMED_AT.isoformat(),
                 "calculation_fingerprint": "b" * 64, "prompt_revision": "skill-groups.v1",
                 "instructions_sha256": "c" * 64, "response_processing_version": "rp.v1",
                 "extraction_strategy": "skill_groups", "filename": "alex-example.pdf", "reuse_from_run_id": None}
        value.update(changes)
        return value

    def test_completion_fields_save_the_report_match_and_counts(self):
        example = v3_example()
        fields = completion_fields(example["report"], example["extraction_audit"], example["raw_agent_output"])
        self.assertEqual(summarize_match(example["report"])["score"], fields["match_score"])
        self.assertEqual((example["scored_skill_count"], example["unscored_skill_count"]),
                         (fields["scored_skill_count"], fields["unscored_skill_count"]))
        self.assertEqual(example["report"], fields["report"])
        self.assertLessEqual(set(fields), model_columns(SkillGapRunRecord))

    def test_a_report_without_weighted_demand_has_no_match_score(self):
        report = deepcopy(v3_example()["report"])
        for row in report["skills"]:
            row["demand"].update(required_job_count=0, preferred_only_job_count=0)
        self.assertIsNone(completion_fields(report, None, {})["match_score"])

    def test_queued_row_keeps_the_local_run_id_as_a_uuid(self):
        state = self.state(reuse_from_run_id=uuid4().hex)
        row = queued_run_row(state, reviewed_resume(), demand_snapshot_fingerprint="d" * 64, catalog_version="v1",
                             partition_policy_version="p.v1", selection_policy_version="s.v1")
        self.assertEqual(UUID(state["id"]), row["id"])
        self.assertEqual(state["id"], row["id"].hex)
        self.assertEqual(UUID(state["reuse_from_run_id"]), row["reuse_from_run_id"])
        self.assertEqual((STORAGE_SCHEMA_VERSION, "alex-example.pdf", CONFIRMED_AT),
                         (row["storage_schema_version"], row["resume_filename"], row["confirmed_at"]))
        self.assertEqual(reviewed_resume(), row["reviewed_resume_snapshot"])
        missing = model_columns(SkillGapRunRecord) - set(row)
        self.assertEqual(missing, set(completion_fields(v3_example()["report"], None, {})) | {
            "agent_name", "agent_version", "completed_at", "elapsed_seconds", "model_calls", "error", "error_code",
            "timings"})

    def test_branch_row_reads_tokens_and_model_from_the_raw_response(self):
        payload = {"job_family": "software_engineer", "core_skills": []}
        raw = {"model": "gpt-5-mini", "reasoning": {"effort": "medium"},
               "usage": {"input_tokens": 6900, "input_tokens_details": {"cached_tokens": 3200},
                         "output_tokens": 2600, "output_tokens_details": {"reasoning_tokens": 1900}}}
        state = {"status": "completed", "agent_name": "fixture-foundation", "agent_version": "1",
                 "model_calls": 1, "elapsed_seconds": 1.5, "reused": False, "error_code": None}
        row = branch_row(RUN_ID, "foundation", state, payload=payload, output={"task": "x"}, raw_response=raw,
                         timings={"inference_seconds": 1.2}, validation={"status": "passed"})
        self.assertEqual(("gpt-5-mini", "medium", 6900, 3200, 2600, 1900, 1.2),
                         (row["model"], row["reasoning_effort"], row["input_tokens"], row["cached_tokens"],
                          row["output_tokens"], row["reasoning_tokens"], row["inference_seconds"]))
        self.assertEqual(canonical_sha256(payload), row["input_sha256"])
        self.assertEqual(model_columns(SkillGapRunBranch) - _SERVER_FILLED, set(row))

    def test_a_reused_branch_records_no_new_tokens(self):
        state = {"status": "completed", "model_calls": 0, "reused": True, "source_run_id": uuid4().hex}
        raw = {"model": "gpt-5-mini", "usage": {"input_tokens": 6900, "output_tokens": 2600}}
        row = branch_row(RUN_ID, "systems", state, raw_response=raw,
                         definition={"model": "fixture-model", "reasoning": {"effort": "medium"}})
        self.assertEqual((None, None, 0, True), (row["input_tokens"], row["output_tokens"], row["model_calls"], row["reused"]))
        self.assertEqual(("fixture-model", "medium"), (row["model"], row["reasoning_effort"]))
        self.assertEqual(UUID(state["source_run_id"]), row["source_run_id"])

    def test_only_the_three_groups_are_branches(self):
        with self.assertRaises(ValueError):
            branch_row(RUN_ID, "other", {"status": "completed"})

    def test_run_uuid_accepts_hex_and_none(self):
        identifier = uuid4().hex
        self.assertEqual(UUID(identifier), run_uuid(identifier))
        self.assertIsNone(run_uuid(None))


class MappingAThreeGroupRunTests(unittest.TestCase):
    """A real (synthetic-transport) three-group run, mapped to rows that satisfy the contract."""

    @staticmethod
    def invoke(payload, save, on_request, timings):
        on_request()
        output = absent_response(payload)
        claim = next(unit for source in payload["resume_sources"] for unit in source["units"] if unit["kind"] == "claim")
        listed_sql = next(unit for source in payload["resume_sources"] for unit in source["units"] if unit["text"] == "SQL")
        if "programming" in output["result"]:
            output["result"]["programming"] = {
                "kind": "practice", "operation_id": claim["id"],
                "capability": {"relation": "direct_personal", "quote": "Implemented an API in Python"},
                "application": "concrete_action",
                "method": None,
                "validation": {"kind": "check_only", "check": {"unit_id": claim["id"], "quote": "unit tests"},
                               "finding": None, "finding_type": None, "reference": None, "reported_value": None,
                               "relation": "same_capability"}}
        if "relational_sql" in output["result"]:
            output["result"]["relational_sql"] = {"kind": "knowledge", "evidence_id": listed_sql["id"]}
        return output

    def test_rows_from_a_completed_run_satisfy_the_contract(self):
        with TemporaryDirectory() as directory:
            manager = group_manager(Path(directory), invoker=self.invoke)
            try:
                run = wait_for(manager, manager.submit(
                    user_id=USER_ID, resume_id=RESUME_ID, reviewed_resume=reviewed_resume(),
                    filename="alex-example.pdf", confirmed_at=CONFIRMED_AT, job_family="software_engineer"))
                self.assertEqual("completed", run.status, run.error)
                audit = load(Path(directory) / run.id / "extraction_audit.json")
                merged = load(Path(directory) / run.id / "agent.response.json")
            finally:
                manager.close()
        rows = result_rows(run.report, audit, run_id=run_uuid(run.id), user_id=USER_ID, job_family="software_engineer")
        by_skill = {row["skill_id"]: row for row in rows}
        self.assertEqual(["capability", "check"], [item["role"] for item in by_skill["programming"]["evidence"]])
        self.assertEqual("Implemented an API in Python", by_skill["programming"]["evidence"][0]["quote"])
        self.assertEqual(["knowledge"], [item["role"] for item in by_skill["relational_sql"]["evidence"]])
        self.assertEqual({"foundation", "lifecycle", "systems"}, {row["branch"] for row in rows})

        fields = completion_fields(run.report, audit, merged)
        self.assertEqual(run.match.score if run.match else None, fields["match_score"])
        record = deepcopy(v3_example())
        record.update(report=run.report, raw_agent_output=merged, extraction_audit=audit,
                      results=[as_contract_row(row) for row in rows],
                      match_score=fields["match_score"], scored_skill_count=fields["scored_skill_count"],
                      unscored_skill_count=fields["unscored_skill_count"])
        Draft202012Validator(contract(), format_checker=FormatChecker()).validate(json.loads(json.dumps(record)))


if __name__ == "__main__":
    unittest.main()
