"""The storage contract: v3 database rows, while v1 single-Agent and v2 group records stay valid."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"


class StorageContractCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((CONTRACTS / "skill-gap-run-storage.schema.json").read_text(encoding="utf-8"))
        cls.v1 = json.loads((CONTRACTS / "skill-gap-run-storage.example.json").read_text(encoding="utf-8"))
        cls.v2 = json.loads((CONTRACTS / "skill-gap-run-storage-v2.example.json").read_text(encoding="utf-8"))
        cls.v3 = json.loads((CONTRACTS / "skill-gap-run-storage-v3.example.json").read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def test_schema_and_all_versioned_examples_are_valid(self):
        Draft202012Validator.check_schema(self.schema)
        self.validator.validate(self.v1)
        self.validator.validate(self.v2)
        self.validator.validate(self.v3)
        self.assertEqual(self.v1["storage_schema_version"], "careergps.skill_gap_run_storage.v1")
        self.assertEqual(self.v2["model_calls"], 3)
        self.assertEqual(self.v2["model_calls"], sum(b["model_calls"] for b in self.v2["branches"].values()))

    def test_v2_accepts_zero_to_three_new_calls_including_cache_reuse(self):
        for count in range(4):
            with self.subTest(count=count):
                value = deepcopy(self.v2)
                value["model_calls"] = count
                for index, branch in enumerate(value["branches"].values()):
                    branch.update(model_calls=int(index < count), reused=index >= count)
                self.validator.validate(value)

    def test_v2_rejects_four_calls_or_more_than_one_request_per_group(self):
        for mutate in (lambda value: value.update(model_calls=4),
                       lambda value: value["branches"]["foundation"].update(model_calls=2)):
            value = deepcopy(self.v2)
            mutate(value)
            with self.assertRaises(ValidationError):
                self.validator.validate(value)

    def test_historical_v1_keeps_its_original_single_call_limit(self):
        for count in (0, 1):
            value = deepcopy(self.v1)
            value["model_calls"] = count
            self.validator.validate(value)
        value["model_calls"] = 3
        with self.assertRaises(ValidationError):
            self.validator.validate(value)

    def test_v2_requires_all_three_group_bindings_and_the_partition_policy(self):
        for mutate in (lambda value: value.pop("branches"),
                       lambda value: value["branches"].pop("systems"),
                       lambda value: value.pop("partition_policy_version"),
                       lambda value: value.update(partition_policy_version="resume-section-partitions.v1")):
            value = deepcopy(self.v2)
            mutate(value)
            with self.assertRaises(ValidationError):
                self.validator.validate(value)

    def test_single_agent_reference_cannot_misrepresent_a_v2_run(self):
        value = deepcopy(self.v2)
        value["agent_name"] = "one-agent-only"
        with self.assertRaises(ValidationError):
            self.validator.validate(value)

    def test_v1_shape_cannot_claim_group_metadata(self):
        value = deepcopy(self.v1)
        value["branches"] = deepcopy(self.v2["branches"])
        with self.assertRaises(ValidationError):
            self.validator.validate(value)

    def test_completion_prerequisites_are_preserved_for_every_version(self):
        for original in (self.v1, self.v2, self.v3):
            for mutate in (lambda value: value.update(report=None),
                           lambda value: value.update(completed_at=None),
                           lambda value: value.update(phase="agent")):
                value = deepcopy(original)
                mutate(value)
                with self.subTest(version=original["storage_schema_version"], value=value["phase"]):
                    with self.assertRaises(ValidationError):
                        self.validator.validate(value)


class StorageContractV3Tests(unittest.TestCase):
    """v3 = what PostgreSQL stores: the run, one branch row per group and one result row per skill."""

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((CONTRACTS / "skill-gap-run-storage.schema.json").read_text(encoding="utf-8"))
        cls.v1 = json.loads((CONTRACTS / "skill-gap-run-storage.example.json").read_text(encoding="utf-8"))
        cls.v2 = json.loads((CONTRACTS / "skill-gap-run-storage-v2.example.json").read_text(encoding="utf-8"))
        cls.v3 = json.loads((CONTRACTS / "skill-gap-run-storage-v3.example.json").read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def assertInvalid(self, value):
        with self.assertRaises(ValidationError):
            self.validator.validate(value)

    def result(self, value, skill_id):
        return next(row for row in value["results"] if row["skill_id"] == skill_id)

    def test_example_results_match_the_report_one_row_per_skill(self):
        report = self.v3["report"]
        self.assertEqual([row["skill_id"] for row in self.v3["results"]],
                         [row["skill_id"] for row in report["skills"]])
        self.assertEqual([row["position"] for row in self.v3["results"]], list(range(len(report["skills"]))))
        self.assertEqual(self.v3["scored_skill_count"] + self.v3["unscored_skill_count"], len(report["skills"]))
        ranked = sorted((row for row in self.v3["results"] if row["priority_rank"]), key=lambda row: row["priority_rank"])
        self.assertEqual([row["skill_id"] for row in ranked], report["priority_order"])

    def test_example_evidence_quotes_are_exact_source_spans(self):
        sources = self.v3["report"]["source_index"]
        quoted = [item for row in self.v3["results"] for item in row["evidence"]]
        self.assertTrue(quoted)
        for item in quoted:
            with self.subTest(skill=item["unit_id"], role=item["role"]):
                unit = sources[item["unit_id"]]
                self.assertEqual(unit["text"][item["start"]:item["end"]], item["quote"])
                self.assertEqual((item["activity_id"], item["source_path"]), (unit["activity_id"], unit["path"]))
        self.assertEqual([item["role"] for item in self.result(self.v3, "programming")["evidence"]],
                         ["capability", "method", "check"])

    def test_branch_rows_keep_raw_answers_for_their_own_skills_only(self):
        assigned = set()
        for name, branch in self.v3["branches"].items():
            skills = set(branch["raw_output"]["result"]) - {"job_family"}
            with self.subTest(branch=name):
                self.assertTrue(skills)
                self.assertTrue(skills.isdisjoint(assigned))
                self.assertEqual({row["skill_id"] for row in self.v3["results"] if row["branch"] == name}, skills)
            assigned |= skills
        self.assertEqual(self.v3["model_calls"], sum(b["model_calls"] for b in self.v3["branches"].values()))

    def test_v3_requires_its_database_fields(self):
        for name in ("results", "match_score", "resume_filename", "branches", "extraction_audit",
                     "selection_policy_version", "scored_skill_count"):
            value = deepcopy(self.v3)
            value.pop(name)
            with self.subTest(missing=name):
                self.assertInvalid(value)

    def test_scored_rows_need_numbers_and_unconfirmed_rows_have_none(self):
        scored = next(row["skill_id"] for row in self.v3["results"] if row["calculation_state"] == "scored")
        pending = next(row["skill_id"] for row in self.v3["results"]
                       if row["calculation_state"] == "needs_confirmation")
        for skill_id, field, bad in ((scored, "grade", None), (scored, "evidence_strength", None),
                                     (scored, "priority", None), (pending, "skill_gap", 0.5),
                                     (pending, "priority_rank", 1), (scored, "grade", "E"),
                                     (scored, "skill_gap", 1.5)):
            value = deepcopy(self.v3)
            self.result(value, skill_id)[field] = bad
            with self.subTest(skill=skill_id, field=field, value=bad):
                self.assertInvalid(value)

    def test_evidence_items_have_a_known_role_and_no_extra_fields(self):
        for mutate in (lambda item: item.update(role="summary"), lambda item: item.update(note="x"),
                       lambda item: item.pop("quote")):
            value = deepcopy(self.v3)
            mutate(self.result(value, "programming")["evidence"][0])
            self.assertInvalid(value)

    def test_an_unfinished_v3_run_has_no_results_or_match(self):
        value = deepcopy(self.v3)
        value.update(status="running", phase="agent", completed_at=None, report=None)
        self.assertInvalid(value)
        value.update(results=[], match_score=None)
        self.validator.validate(value)

    def test_v3_is_a_group_run_and_older_versions_cannot_claim_v3_fields(self):
        value = deepcopy(self.v3)
        value["agent_name"] = "one-agent-only"
        self.assertInvalid(value)
        value = deepcopy(self.v3)
        value["extraction_strategy"] = "single"
        self.assertInvalid(value)
        for older in (self.v1, self.v2):
            value = deepcopy(older)
            value["results"] = []
            with self.subTest(version=older["storage_schema_version"]):
                self.assertInvalid(value)


if __name__ == "__main__":
    unittest.main()
