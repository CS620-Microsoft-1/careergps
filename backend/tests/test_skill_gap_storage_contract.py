"""The proposed v2 storage mapping preserves historical single-Agent records."""
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
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def test_schema_and_both_versioned_examples_are_valid(self):
        Draft202012Validator.check_schema(self.schema)
        self.validator.validate(self.v1)
        self.validator.validate(self.v2)
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

    def test_completion_prerequisites_are_preserved_for_both_versions(self):
        for original in (self.v1, self.v2):
            for mutate in (lambda value: value.update(report=None),
                           lambda value: value.update(completed_at=None),
                           lambda value: value.update(phase="agent")):
                value = deepcopy(original)
                mutate(value)
                with self.subTest(version=original["storage_schema_version"], value=value["phase"]):
                    with self.assertRaises(ValidationError):
                        self.validator.validate(value)


if __name__ == "__main__":
    unittest.main()
