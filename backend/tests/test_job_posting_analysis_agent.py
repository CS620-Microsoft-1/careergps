"""Offline contract and client tests; all Azure entry points are replaced with fakes."""

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.job_posting_analysis import (
    JobPostingAnalysisValidationError,
    validate_analysis_response,
)
from app.services.job_posting_analysis_agent import (
    FoundryJobPostingAnalysisService,
    JobPostingAnalysisAgentError,
    JobPostingAnalysisInputError,
    ARRAY_FIELDS,
    COPIED_METADATA_FIELDS,
    SCALAR_FIELDS,
    JobPostingAnalysisContentValidationError,
    validate_analysis_content,
)


JOB_ID = "10000000-0000-4000-8000-000000000001"
ENDPOINT = "https://example.test/api/projects/jd-test"
DESCRIPTION = "Must have Python or Go. Base salary: $100,000–$120,000 per year."


def posting_fixture() -> dict:
    return {
        "id": JOB_ID,
        "source": "greenhouse",
        "external_id": "example-1",
        "company_slug": "example",
        "company_name": "Example",
        "company_tier": "other",
        "title": "Software Engineer",
        "location": "Example City",
        "country": None,
        "workplace_type": None,
        "department": None,
        "employment_type": None,
        "description_text": DESCRIPTION,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_interval": None,
        "url": "https://example.test/jobs/1?source=test&lang=en",
        "published_at": None,
        "first_seen_at": "2026-10-20T12:34:56.123456+00:00",
        "last_seen_at": "2026-10-20T12:34:56.123456+00:00",
        "closed_at": None,
        "content_hash": "0" * 64,
        "created_at": "2026-10-20T12:34:56.123456+00:00",
        "updated_at": "2026-10-20T12:34:56.123456+00:00",
    }


def analysis_fixture() -> dict:
    source = posting_fixture()
    scalar_fields = (
        "id", "source", "external_id", "company_slug", "company_name", "company_tier",
        "job_title", "job_family", "seniority", "department", "role_overview",
        "salary_currency", "salary_interval", "url", "published_at", "first_seen_at",
        "last_seen_at", "closed_at", "content_hash", "created_at", "updated_at",
    )
    array_fields = (
        "locations", "responsibilities", "qualifications", "job_conditions",
        "compensation", "benefits", "other_relevant_information",
    )
    payload = {field: {"value": None, "evidence": []} for field in scalar_fields}
    payload.update({field: [] for field in array_fields})
    for field in (
        "id", "source", "external_id", "company_slug", "company_name", "company_tier",
        "url", "published_at", "first_seen_at", "last_seen_at", "closed_at", "content_hash",
        "created_at", "updated_at",
    ):
        if source[field] is not None:
            payload[field] = {
                "value": source[field],
                "evidence": [{"source_field": field, "quote": source[field]}],
            }
    payload["job_title"] = {
        "value": source["title"],
        "evidence": [{"source_field": "title", "quote": source["title"]}],
    }
    payload["qualifications"] = [{
        "value": "Must have Python or Go.",
        "level": "required",
        "categories": ["skill"],
        "evidence": [{"source_field": "description_text", "quote": "Must have Python or Go."}],
    }]
    payload["compensation"] = [{
        "type": "base_salary",
        "value": "Base salary: $100,000–$120,000 per year.",
        "minimum": 100000,
        "maximum": 120000,
        "currency": None,
        "interval": "year",
        "applies_to": None,
        "evidence": [{
            "source_field": "description_text",
            "quote": "Base salary: $100,000–$120,000 per year.",
        }],
    }]
    return payload


class AnalysisValidationTests(unittest.TestCase):
    def validate(self, text: str) -> dict:
        return validate_analysis_response(text, job_posting_id=JOB_ID)

    def test_complete_result_is_preserved_without_normalization(self) -> None:
        payload = analysis_fixture()
        self.assertEqual(28, len(payload))
        original = deepcopy(payload)
        result = self.validate(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(original, result)
        self.assertIn("Python or Go", result["qualifications"][0]["value"])
        self.assertIn("$100,000", result["compensation"][0]["value"])
        self.assertEqual(100000, result["compensation"][0]["minimum"])

    def test_rejects_non_json_fences_and_invalid_dollar_escape(self) -> None:
        encoded = json.dumps(analysis_fixture())
        for text in (
            "", "not json", f"```json\n{encoded}\n```", f"prefix {encoded}",
            encoded.replace("$100,000", r"\$100,000"),
        ):
            with self.subTest(text=text[:25]):
                with self.assertRaises(JobPostingAnalysisValidationError):
                    self.validate(text)

    def test_rejects_duplicate_keys_at_any_depth(self) -> None:
        encoded = json.dumps(analysis_fixture())
        for text in (
            encoded.replace('{"id":', '{"id": null, "id":', 1),
            encoded.replace('"minimum": 100000', '"minimum": 0, "minimum": 100000', 1),
        ):
            with self.subTest(text=text[:50]):
                with self.assertRaises(JobPostingAnalysisValidationError):
                    self.validate(text)

    def test_rejects_nonfinite_numbers_including_overflow(self) -> None:
        encoded = json.dumps(analysis_fixture())
        for token in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
            with self.subTest(token=token):
                text = encoded.replace('"minimum": 100000', f'"minimum": {token}', 1)
                with self.assertRaises(JobPostingAnalysisValidationError):
                    self.validate(text)

    def test_rejects_missing_or_extra_top_level_fields(self) -> None:
        missing = analysis_fixture()
        missing.pop("benefits")
        extra = analysis_fixture()
        extra["invented"] = []
        for payload in (missing, extra):
            with self.subTest(keys=len(payload)):
                with self.assertRaises(JobPostingAnalysisValidationError):
                    self.validate(json.dumps(payload))

    def test_rejects_invalid_nested_types_and_enums(self) -> None:
        wrong_enum = analysis_fixture()
        wrong_enum["qualifications"][0]["level"] = "mandatory"
        wrong_type = analysis_fixture()
        wrong_type["compensation"][0]["minimum"] = "100000"
        missing_evidence = analysis_fixture()
        missing_evidence["qualifications"][0].pop("evidence")
        for payload in (wrong_enum, wrong_type, missing_evidence):
            with self.subTest(payload=payload["qualifications"]):
                with self.assertRaises(JobPostingAnalysisValidationError):
                    self.validate(json.dumps(payload))

    def test_rejects_another_posting_id(self) -> None:
        payload = analysis_fixture()
        payload["id"]["value"] = "10000000-0000-4000-8000-000000000002"
        with self.assertRaises(JobPostingAnalysisValidationError):
            self.validate(json.dumps(payload))

    def test_rejects_non_object_roots(self) -> None:
        for text in ("[]", "null", '"text"', "42"):
            with self.subTest(text=text):
                with self.assertRaises(JobPostingAnalysisValidationError):
                    self.validate(text)


class FoundryJobPostingAnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        # Fake the entire import hierarchy before analyze() can import the SDK.
        # There is no real credential construction, HTTP client or database import.
        modules = {name: ModuleType(name) for name in (
            "azure", "azure.ai", "azure.ai.projects", "azure.identity",
        )}
        for name in ("azure", "azure.ai"):
            modules[name].__path__ = []
        modules["azure"].ai = modules["azure.ai"]
        modules["azure"].identity = modules["azure.identity"]
        modules["azure.ai"].projects = modules["azure.ai.projects"]

        self.credential = MagicMock(name="fake_credential")
        self.project = MagicMock(name="fake_project")
        self.client = MagicMock(name="fake_openai_client")
        for context in (self.credential, self.project, self.client):
            context.__enter__.return_value = context
        self.credential_factory = MagicMock(return_value=self.credential)
        self.project_factory = MagicMock(return_value=self.project)
        modules["azure.identity"].DefaultAzureCredential = self.credential_factory
        modules["azure.ai.projects"].AIProjectClient = self.project_factory
        self.project.get_openai_client.return_value = self.client
        self.client.conversations.create.return_value = SimpleNamespace(id="conversation-1")
        self.client.responses.create.return_value = SimpleNamespace(
            status="completed", output_text=json.dumps(analysis_fixture(), ensure_ascii=False),
        )
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.service = FoundryJobPostingAnalysisService(ENDPOINT)

    def test_sends_all_input_fields_and_uses_only_fixed_version_ten(self) -> None:
        posting = posting_fixture()
        before = deepcopy(posting)
        result = self.service.analyze(posting)

        self.assertEqual(before, posting)
        self.assertEqual(25, len(posting))
        self.assertEqual(analysis_fixture(), result)
        self.project_factory.assert_called_once_with(
            endpoint=ENDPOINT, credential=self.credential,
        )
        self.project.get_openai_client.assert_called_once_with(
            timeout=600.0, max_retries=0,
        )
        call = self.client.responses.create.call_args
        self.assertEqual((), call.args)
        self.assertEqual({"conversation", "input", "extra_body"}, set(call.kwargs))
        self.assertEqual("conversation-1", call.kwargs["conversation"])
        self.assertEqual({"agent_reference": {
            "type": "agent_reference", "name": "job-analysis-agent", "version": "10",
        }}, call.kwargs["extra_body"])
        messages = call.kwargs["input"]
        self.assertEqual(1, len(messages))
        self.assertEqual("user", messages[0]["role"])
        self.assertEqual(posting, json.loads(messages[0]["content"]))
        self.client.conversations.delete.assert_called_once_with(
            conversation_id="conversation-1",
        )

    def test_each_analysis_uses_an_independent_conversation(self) -> None:
        self.client.conversations.create.side_effect = [
            SimpleNamespace(id="conversation-1"), SimpleNamespace(id="conversation-2"),
        ]
        self.service.analyze(posting_fixture())
        self.service.analyze(posting_fixture())
        self.assertEqual(2, self.client.conversations.create.call_count)
        self.assertEqual([
            "conversation-1", "conversation-2",
        ], [call.kwargs["conversation"] for call in self.client.responses.create.call_args_list])
        self.assertEqual(2, self.client.conversations.delete.call_count)

    def test_missing_endpoint_fails_before_constructing_any_sdk_client(self) -> None:
        for endpoint in (None, "", "   "):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(JobPostingAnalysisAgentError):
                    FoundryJobPostingAnalysisService(endpoint).analyze(posting_fixture())
        self.credential_factory.assert_not_called()
        self.project_factory.assert_not_called()

    def test_invalid_input_fails_before_constructing_any_sdk_client(self) -> None:
        invalid = [None, [], "posting"]
        for field in ("id", "description_text"):
            for value in (None, "", "   ", 7):
                posting = posting_fixture()
                posting[field] = value
                invalid.append(posting)
            missing = posting_fixture()
            missing.pop(field)
            invalid.append(missing)
        for posting in invalid:
            with self.subTest(input_type=type(posting).__name__):
                with self.assertRaises(JobPostingAnalysisInputError):
                    self.service.analyze(posting)
        self.credential_factory.assert_not_called()
        self.project_factory.assert_not_called()

    def test_nonserializable_and_nonfinite_inputs_are_rejected_locally(self) -> None:
        for value in (object(), float("nan"), float("inf")):
            posting = posting_fixture()
            posting["extra"] = value
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(JobPostingAnalysisInputError):
                    self.service.analyze(posting)
        self.credential_factory.assert_not_called()
        self.project_factory.assert_not_called()

    def test_non_completed_response_is_rejected_and_conversation_is_cleaned(self) -> None:
        for status in ("incomplete", "failed", "cancelled", "in_progress", None):
            with self.subTest(status=status):
                self.client.responses.create.return_value.status = status
                with self.assertRaises(JobPostingAnalysisAgentError):
                    self.service.analyze(posting_fixture())
        self.assertEqual(5, self.client.conversations.delete.call_count)

    def test_invalid_response_is_rejected_without_repair_and_is_cleaned(self) -> None:
        self.client.responses.create.return_value.output_text = "```json\n{}\n```"
        with self.assertRaises(JobPostingAnalysisValidationError):
            self.service.analyze(posting_fixture())
        self.client.conversations.delete.assert_called_once_with(
            conversation_id="conversation-1",
        )

    def test_sdk_error_is_sanitized_and_conversation_is_cleaned(self) -> None:
        private_text = "PRIVATE_JD_AND_RESPONSE_MUST_NOT_BE_EXPOSED"
        self.client.responses.create.side_effect = RuntimeError(private_text)
        with self.assertRaises(JobPostingAnalysisAgentError) as caught:
            self.service.analyze(posting_fixture())
        self.assertNotIn(private_text, str(caught.exception))
        self.assertNotIn(DESCRIPTION, str(caught.exception))
        self.assertEqual(1, self.client.responses.create.call_count)
        self.client.conversations.delete.assert_called_once_with(
            conversation_id="conversation-1",
        )

    def test_cleanup_failure_does_not_discard_successful_result(self) -> None:
        self.client.conversations.delete.side_effect = RuntimeError("cleanup failed")
        self.assertEqual(analysis_fixture(), self.service.analyze(posting_fixture()))

    def test_cleanup_failure_does_not_mask_validation_failure(self) -> None:
        self.client.responses.create.return_value.output_text = "not json"
        self.client.conversations.delete.side_effect = RuntimeError("cleanup failed")
        with self.assertRaises(JobPostingAnalysisValidationError):
            self.service.analyze(posting_fixture())

    def test_client_construction_error_is_sanitized_without_fallback(self) -> None:
        self.project_factory.side_effect = RuntimeError("PRIVATE_ENDPOINT_ERROR")
        with self.assertRaises(JobPostingAnalysisAgentError) as caught:
            self.service.analyze(posting_fixture())
        self.assertNotIn("PRIVATE_ENDPOINT_ERROR", str(caught.exception))
        self.assertEqual(1, self.project_factory.call_count)
        self.client.responses.create.assert_not_called()


class JobPostingAnalysisSettingsTests(unittest.TestCase):
    def test_jd_settings_are_independent_of_resume_settings(self) -> None:
        from app.core.config import Settings

        settings_values = {
            "_env_file": None,
            "database_url": "postgresql+psycopg://test:unused@127.0.0.1:1/test",
            "foundry_project_endpoint": "https://resume.example.test",
            "job_analysis_project_endpoint": "https://jd.example.test",
            "job_analysis_timeout_seconds": 600.0,
        }
        settings = Settings(**settings_values)
        self.assertEqual("https://resume.example.test", settings.foundry_project_endpoint)
        self.assertEqual("https://jd.example.test", settings.job_analysis_project_endpoint)
        self.assertEqual(600.0, settings.job_analysis_timeout_seconds)
        for timeout in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    Settings(**{**settings_values, "job_analysis_timeout_seconds": timeout})


# Exact evidence, copied metadata, and compensation checks share this boundary.
CONTENT_JOB_ID = "7d7afc23-e5f7-42a1-b571-755202eb7f83"


def evidence(field: str, quote: str) -> list[dict[str, str]]:
    return [{"source_field": field, "quote": quote}]


def content_posting_fixture() -> dict:
    return {
        "id": CONTENT_JOB_ID,
        "source": "greenhouse",
        "external_id": "00123",
        "company_slug": "example",
        "company_tier": "other",
        "url": "https://example.invalid/jobs?id=00123&lang=en#apply",
        "published_at": "2026-10-20T10:01:02.123400+00:00",
        "first_seen_at": "2026-10-20T10:01:02.123400+00:00",
        "last_seen_at": "2026-10-20T10:01:02.123400+00:00",
        "closed_at": None,
        "content_hash": "a" * 64,
        "created_at": "2026-10-20T10:01:02.123400+00:00",
        "updated_at": "2026-10-20T10:01:02.123400+00:00",
        "title": "Senior Engineer, Payments",
        "company_name": "Example Company LLC",
        "department": None,
        "description_text": (
            "Required:\nPython or Scala.\nBuild systems for millions of users.\n"
            "Base salary: $100,000–$150,000 USD per year.\n"
            "Europe base pay: EUR 90,000–120,000 per year.\n"
            "Medical coverage and paid leave. Café — 東京\r\nHybrid team."
        ),
        "salary_min": 100000,
        "salary_max": 150000,
        "salary_currency": "USD",
        "salary_interval": "year",
    }


def content_payload_fixture(posting: dict | None = None) -> dict:
    posting = content_posting_fixture() if posting is None else posting
    result = {field: {"value": None, "evidence": []} for field in SCALAR_FIELDS}
    result.update({field: [] for field in ARRAY_FIELDS})
    for field in COPIED_METADATA_FIELDS:
        value = posting.get(field)
        if value is not None and value != "":
            result[field] = {"value": value, "evidence": evidence(field, value)}
    return result


def compensation(**changes) -> dict:
    item = {
        "type": "base_salary",
        "value": "Base salary: $100,000–$150,000 USD per year.",
        "minimum": 100000,
        "maximum": 150000,
        "currency": "USD",
        "interval": "year",
        "applies_to": None,
        "evidence": evidence("description_text", "Base salary: $100,000–$150,000 USD per year."),
    }
    item.update(changes)
    return item


class JobPostingAnalysisContentValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.posting = content_posting_fixture()
        self.payload = content_payload_fixture(self.posting)

    def validate(self) -> None:
        # Each fixture is also accepted by the unchanged strict v10 schema.
        parsed = validate_analysis_response(json.dumps(self.payload), job_posting_id=CONTENT_JOB_ID)
        validate_analysis_content(parsed, posting=self.posting)

    def assert_problem(self, code: str, path: str | None = None) -> JobPostingAnalysisContentValidationError:
        with self.assertRaises(JobPostingAnalysisContentValidationError) as context:
            self.validate()
        errors = context.exception.issues
        self.assertTrue(any(issue.code == code and (path is None or issue.path == path) for issue in errors))
        return context.exception

    def test_valid_metadata_only_payload_and_no_mutation(self) -> None:
        original_posting, original_payload = deepcopy(self.posting), deepcopy(self.payload)
        self.validate()
        self.assertEqual(self.posting, original_posting)
        self.assertEqual(self.payload, original_payload)
        self.assertEqual(len(self.payload), 28)

    def test_non_null_scalar_needs_evidence(self) -> None:
        self.payload["department"] = {"value": "Payments", "evidence": []}
        self.assert_problem("missing_evidence", "/department/evidence")

    def test_empty_and_whitespace_scalar_values_are_rejected(self) -> None:
        for value in ("", " \t\n"):
            with self.subTest(value=repr(value)):
                self.payload["department"] = {"value": value, "evidence": evidence("title", "Payments")}
                self.assert_problem("empty_value", "/department/value")

    def test_null_scalar_must_have_empty_evidence(self) -> None:
        self.payload["department"]["evidence"] = evidence("title", "Payments")
        self.assert_problem("null_value_has_evidence", "/department/evidence")

    def test_every_array_item_requires_nonempty_value_and_evidence(self) -> None:
        factories = {
            "locations": {}, "responsibilities": {}, "benefits": {}, "other_relevant_information": {},
            "qualifications": {"level": "required", "categories": ["skill"]},
            "job_conditions": {"type": "other"},
            "compensation": {key: value for key, value in compensation().items() if key not in ("value", "evidence")},
        }
        for field, extra in factories.items():
            with self.subTest(field=field):
                self.payload = content_payload_fixture(self.posting)
                self.payload[field] = [{**extra, "value": " ", "evidence": []}]
                self.assert_problem("empty_value", f"/{field}/0/value")
                self.assert_problem("missing_evidence", f"/{field}/0/evidence")

    def test_empty_or_whitespace_quote_rejected(self) -> None:
        for quote in ("", " \n"):
            self.payload["job_title"] = {"value": "Engineer", "evidence": evidence("title", quote)}
            self.assert_problem("empty_evidence_quote", "/job_title/evidence/0/quote")

    def test_unknown_source_field_rejected_without_disclosing_its_name(self) -> None:
        private = "private_secret_field_123456"
        self.payload["job_title"] = {"value": "Engineer", "evidence": evidence(private, "private_raw_quote_9876")}
        error = self.assert_problem("unknown_evidence_source")
        self.assertNotIn(private, str(error))
        self.assertNotIn("private_raw_quote_9876", str(error))
        self.assertIsInstance(error, JobPostingAnalysisValidationError)

    def test_null_array_and_object_sources_are_not_evidence(self) -> None:
        for source in (None, ["Payments"], {"value": "Payments"}):
            with self.subTest(source=source):
                self.posting["arbitrary_input"] = source
                self.payload["department"] = {"value": "Payments", "evidence": evidence("arbitrary_input", "Payments")}
                self.assert_problem("unsupported_evidence_source")

    def test_exact_unicode_and_crlf_quote_after_json_decoding(self) -> None:
        self.payload["role_overview"] = {
            "value": "Café — 東京; Hybrid team.",
            "evidence": evidence("description_text", "Café — 東京\r\nHybrid team."),
        }
        self.validate()

    def test_quotes_not_case_whitespace_punctuation_or_unicode_normalized(self) -> None:
        quotes = ("café — 東京", "Café — 東京\nHybrid team.", "Café - 東京", "Cafe\u0301 — 東京")
        for quote in quotes:
            with self.subTest(quote=quote):
                self.payload["role_overview"] = {"value": "Team", "evidence": evidence("description_text", quote)}
                self.assert_problem("evidence_quote_not_in_source")

    def test_noncontiguous_quote_cannot_be_spliced(self) -> None:
        self.payload["role_overview"] = {
            "value": "Python or Scala and medical coverage.",
            "evidence": evidence("description_text", "Python or Scala. Medical coverage"),
        }
        self.assert_problem("evidence_quote_not_in_source")

    def test_separate_contiguous_excerpts_are_allowed(self) -> None:
        self.payload["role_overview"] = {
            "value": "Python or Scala; medical coverage.",
            "evidence": evidence("description_text", "Python or Scala.") + evidence("description_text", "Medical coverage"),
        }
        self.validate()

    def test_dollar_quote_remains_plain_dollar(self) -> None:
        self.payload["compensation"] = [compensation()]
        self.validate()
        self.assertNotIn("\\$", json.dumps(self.payload))

    def test_inserted_literal_backslash_before_dollar_is_rejected_without_repair(self) -> None:
        self.payload["compensation"] = [compensation()]
        self.payload["compensation"][0]["evidence"][0]["quote"] = "Base salary: \\$100,000"
        before = deepcopy(self.payload)
        self.assert_problem("evidence_quote_not_in_source")
        self.assertEqual(self.payload, before)

    def test_literal_backslash_in_original_source_is_preserved(self) -> None:
        self.posting["description_text"] = r"Literal source text: \$100"
        self.payload["role_overview"] = {
            "value": r"Literal source text: \$100",
            "evidence": evidence("description_text", r"\$100"),
        }
        self.validate()

    def test_numeric_quotes_use_entire_json_scalar(self) -> None:
        self.payload["role_overview"] = {"value": "Minimum 100000", "evidence": evidence("salary_min", "100000")}
        self.validate()
        self.payload["role_overview"]["evidence"][0]["quote"] = "100"
        self.assert_problem("evidence_scalar_not_exact")

    def test_numeric_float_quotes_do_not_silently_change_representation(self) -> None:
        self.posting["custom_number"] = 100.0
        self.payload["role_overview"] = {"value": "100", "evidence": evidence("custom_number", "100.0")}
        self.validate()
        self.payload["role_overview"]["evidence"][0]["quote"] = "100"
        self.assert_problem("evidence_scalar_not_exact")

    def test_boolean_quotes_require_json_boolean_spelling(self) -> None:
        self.posting["custom_boolean"] = True
        self.payload["role_overview"] = {"value": "Yes", "evidence": evidence("custom_boolean", "true")}
        self.validate()
        for quote in ("True", "1", "tru"):
            self.payload["role_overview"]["evidence"][0]["quote"] = quote
            self.assert_problem("evidence_scalar_not_exact")

    def test_nonfinite_numeric_input_is_not_accepted_as_evidence(self) -> None:
        self.posting["custom_number"] = float("nan")
        self.payload["role_overview"] = {"value": "Not known", "evidence": evidence("custom_number", "NaN")}
        self.assert_problem("unsupported_evidence_source")

    def test_copied_metadata_is_exact_including_url_and_timestamp(self) -> None:
        for field, replacement in (("external_id", "123"), ("published_at", "2026-10-20T10:01:02.1234Z"), ("url", "https://example.invalid/jobs")):
            with self.subTest(field=field):
                self.payload = content_payload_fixture(self.posting)
                self.payload[field]["value"] = replacement
                self.assert_problem("metadata_not_exact_copy", f"/{field}/value")

    def test_copied_metadata_needs_one_full_quote_from_same_input_field(self) -> None:
        variants = (
            [],
            evidence("description_text", "100"),
            evidence("url", "https://example.invalid"),
            evidence("url", self.posting["url"]) * 2,
        )
        for entries in variants:
            with self.subTest(entries=entries):
                self.payload["url"]["evidence"] = entries
                self.assert_problem("metadata_evidence_not_exact", "/url/evidence")

    def test_missing_null_and_empty_metadata_are_null_without_evidence(self) -> None:
        del self.posting["published_at"]
        self.posting["external_id"] = ""
        self.payload = content_payload_fixture(self.posting)
        self.validate()
        self.payload["published_at"] = {"value": "2026-10-20", "evidence": []}
        self.assert_problem("metadata_absent_not_null", "/published_at")

    def test_null_metadata_with_attached_evidence_is_rejected(self) -> None:
        self.payload["closed_at"]["evidence"] = evidence("title", "Engineer")
        self.assert_problem("metadata_absent_not_null", "/closed_at")

    def test_numeric_metadata_is_not_silently_stringified(self) -> None:
        self.posting["external_id"] = 123
        self.payload["external_id"] = {"value": "123", "evidence": evidence("external_id", "123")}
        self.assert_problem("metadata_source_not_string", "/external_id")

    def test_title_company_and_other_values_are_not_forced_to_equal_quotes(self) -> None:
        self.payload["job_title"] = {"value": "Senior Engineer", "evidence": evidence("title", self.posting["title"])}
        self.payload["company_name"] = {"value": "Example Company", "evidence": evidence("company_name", self.posting["company_name"])}
        self.validate()

    def test_categories_require_one_or_more_unique_items(self) -> None:
        for categories, code in (([], "qualification_categories_empty"), (["skill", "skill"], "qualification_categories_duplicate")):
            self.payload["qualifications"] = [{
                "value": "Python or Scala", "level": "required", "categories": categories,
                "evidence": evidence("description_text", "Python or Scala."),
            }]
            self.assert_problem(code, "/qualifications/0/categories")
        self.payload["qualifications"][0]["categories"] = ["skill", "experience"]
        self.validate()

    def test_negative_and_reversed_money_bounds_are_rejected(self) -> None:
        self.payload["compensation"] = [compensation(minimum=-1, maximum=-2)]
        self.assert_problem("negative_monetary_amount", "/compensation/0/minimum")
        self.assert_problem("negative_monetary_amount", "/compensation/0/maximum")
        self.assert_problem("monetary_bounds_reversed", "/compensation/0")

    def test_populated_compensation_string_attributes_cannot_be_blank(self) -> None:
        for attribute in ("currency", "applies_to"):
            with self.subTest(attribute=attribute):
                self.payload["compensation"] = [compensation(**{attribute: " \t"})]
                self.assert_problem("empty_compensation_attribute", f"/compensation/0/{attribute}")

    def test_zero_fixed_and_one_sided_bounds_are_accepted(self) -> None:
        for minimum, maximum in ((0, 0), (None, 150000), (100000, None), (100000, 100000), (None, None)):
            with self.subTest(bounds=(minimum, maximum)):
                self.payload["compensation"] = [compensation(minimum=minimum, maximum=maximum)]
                self.validate()

    def test_common_base_currency_and_interval_must_match_every_arrangement(self) -> None:
        self.payload["compensation"] = [compensation(), compensation(currency="EUR")]
        self.payload["salary_currency"] = {"value": "USD", "evidence": evidence("salary_currency", "USD")}
        self.assert_problem("base_summary_inconsistent", "/salary_currency/value")
        self.payload["salary_currency"] = {"value": None, "evidence": []}
        self.payload["salary_interval"] = {"value": "year", "evidence": evidence("salary_interval", "year")}
        self.validate()
        self.payload["compensation"][1]["interval"] = "month"
        self.assert_problem("base_summary_inconsistent", "/salary_interval/value")

    def test_currency_summary_case_difference_is_equivalent_without_rewriting(self) -> None:
        self.payload["compensation"] = [compensation(currency="usd")]
        self.payload["salary_currency"] = {"value": "USD", "evidence": evidence("salary_currency", "USD")}
        before = deepcopy(self.payload)
        self.validate()
        self.assertEqual(self.payload, before)
        self.assertEqual(self.payload["salary_currency"]["value"], "USD")
        self.assertEqual(self.payload["compensation"][0]["currency"], "usd")

    def test_unknown_item_attribute_prevents_nonnull_common_summary(self) -> None:
        self.payload["compensation"] = [compensation(currency=None, interval=None)]
        self.payload["salary_currency"] = {"value": "USD", "evidence": evidence("salary_currency", "USD")}
        self.payload["salary_interval"] = {"value": "year", "evidence": evidence("salary_interval", "year")}
        self.assert_problem("base_summary_inconsistent", "/salary_currency/value")
        self.assert_problem("base_summary_inconsistent", "/salary_interval/value")

    def test_null_summaries_are_not_forced_to_populate(self) -> None:
        self.payload["compensation"] = [compensation()]
        self.validate()

    def test_nonbase_bonus_equity_and_ote_are_excluded_from_summary_consistency(self) -> None:
        self.payload["compensation"] = [compensation()] + [
            compensation(type=kind, currency="EUR", interval="one_time")
            for kind in ("bonus", "equity", "commission", "ote", "stipend", "other")
        ]
        self.payload["salary_currency"] = {"value": "USD", "evidence": evidence("salary_currency", "USD")}
        self.payload["salary_interval"] = {"value": "year", "evidence": evidence("salary_interval", "year")}
        self.validate()

    def test_hourly_pay_participates_in_common_summary_checks(self) -> None:
        self.payload["compensation"] = [compensation(type="hourly_rate", interval="hour")]
        self.payload["salary_interval"] = {"value": "year", "evidence": evidence("salary_interval", "year")}
        self.assert_problem("base_summary_inconsistent", "/salary_interval/value")

    def test_metadata_only_summaries_can_be_known_without_compensation_amounts(self) -> None:
        self.payload["salary_currency"] = {"value": "USD", "evidence": evidence("salary_currency", "USD")}
        self.payload["salary_interval"] = {"value": "year", "evidence": evidence("salary_interval", "year")}
        self.validate()

    def test_amount_currency_and_interval_are_independent(self) -> None:
        self.payload["compensation"] = [compensation(currency=None, interval=None)]
        self.validate()
        self.payload["compensation"] = [compensation(minimum=None, maximum=None)]
        self.payload["salary_currency"] = {"value": "USD", "evidence": evidence("salary_currency", "USD")}
        self.validate()

    def test_semantic_truth_is_not_claimed_by_exact_quote_checks(self) -> None:
        # Deliberately demonstrates the limit: provenance cannot prove AND/OR fidelity.
        self.payload["qualifications"] = [{
            "value": "Python and Scala", "level": "preferred", "categories": ["skill"],
            "evidence": evidence("description_text", "Python or Scala."),
        }]
        self.validate()

    def test_errors_are_bounded_and_never_contain_raw_values(self) -> None:
        private = "raw_private_quote_value_987654321"
        self.payload["responsibilities"] = [{
            "value": private,
            "evidence": evidence("private_source_field", private),
        }] * 200
        error = self.assert_problem("unknown_evidence_source")
        self.assertEqual(len(error.issues), 100)
        self.assertLess(len(str(error)), 1500)
        self.assertNotIn(private, str(error))
        self.assertNotIn("private_source_field", str(error))
        self.assertIsInstance(error.issues, tuple)


if __name__ == "__main__":
    unittest.main()
