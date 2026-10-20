"""Call the fixed JD Agent and validate its output without rewriting extracted facts."""

from __future__ import annotations

import json
import math
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any

from app.schemas.job_posting_analysis import (
    JobPostingAnalysisValidationError,
    validate_analysis_response,
)

AGENT_NAME = "job-analysis-agent"
AGENT_VERSION = "10"


class JobPostingAnalysisInputError(ValueError):
    """The supplied posting is not ready to send to the Agent."""


class JobPostingAnalysisAgentError(RuntimeError):
    """A sanitized configuration or transport error, without posting content."""


class FoundryJobPostingAnalysisService:
    def __init__(
        self, endpoint: str | None, *, timeout_seconds: float = 600.0
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("The job analysis timeout must be positive and finite.")
        self.endpoint = (endpoint or "").strip()
        self.timeout_seconds = timeout_seconds

    def analyze(self, posting: dict[str, Any]) -> dict[str, Any]:
        """Accept one JSON-ready JP, preserving all its fields and null values."""
        if not isinstance(posting, dict):
            raise JobPostingAnalysisInputError("The posting must be a JSON object.")
        for field in ("id", "description_text"):
            value = posting.get(field)
            if not isinstance(value, str) or not value.strip():
                raise JobPostingAnalysisInputError(
                    f"The posting requires a nonempty string {field}."
                )
        posting_id = posting["id"]
        try:
            content = json.dumps(posting, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise JobPostingAnalysisInputError(
                "The posting must contain JSON-serializable values."
            ) from None
        if not self.endpoint:
            raise JobPostingAnalysisAgentError(
                "Set JOB_ANALYSIS_PROJECT_ENDPOINT before calling the job analysis Agent."
            )

        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError:
            raise JobPostingAnalysisAgentError(
                "The Foundry SDK dependencies are not installed."
            ) from None

        try:
            with ExitStack() as stack:
                credential = stack.enter_context(DefaultAzureCredential())
                project = stack.enter_context(
                    AIProjectClient(endpoint=self.endpoint, credential=credential)
                )
                client = stack.enter_context(
                    project.get_openai_client(
                        timeout=self.timeout_seconds, max_retries=0
                    )
                )
                conversation = client.conversations.create()
                try:
                    response = client.responses.create(
                        conversation=conversation.id,
                        input=[{"role": "user", "content": content}],
                        extra_body={
                            "agent_reference": {
                                "type": "agent_reference",
                                "name": AGENT_NAME,
                                "version": AGENT_VERSION,
                            }
                        },
                    )
                    if getattr(response, "status", None) != "completed":
                        raise JobPostingAnalysisAgentError(
                            "The job analysis Agent did not complete its response."
                        )
                    return validate_analysis_response(
                        getattr(response, "output_text", ""), job_posting_id=posting_id
                    )
                finally:
                    try:
                        client.conversations.delete(conversation_id=conversation.id)
                    except Exception:
                        # Cleanup must not replace a valid result or the original failure.
                        pass
        except (JobPostingAnalysisValidationError, JobPostingAnalysisAgentError):
            raise
        except Exception as error:
            name = type(error).__name__
            status = getattr(error, "status_code", None)
            if status in (401, 403) or "Authentication" in name or "Credential" in name:
                message = "Azure authentication failed. Verify login and Foundry permissions."
            elif status == 404:
                message = "The configured job analysis Agent version 10 was not found."
            elif status == 429 or "RateLimit" in name:
                message = "The job analysis Agent rate limit was reached."
            elif isinstance(error, TimeoutError) or "Timeout" in name:
                message = "The job analysis Agent request timed out."
            else:
                message = "The job analysis Agent request failed."
            raise JobPostingAnalysisAgentError(message) from None


# Deterministic checks are also called by the pipeline against the original JP.
COPIED_METADATA_FIELDS = (
    "id", "source", "external_id", "company_slug", "company_tier", "url",
    "published_at", "first_seen_at", "last_seen_at", "closed_at", "content_hash",
    "created_at", "updated_at",
)
SCALAR_FIELDS = COPIED_METADATA_FIELDS + (
    "company_name", "job_title", "job_family", "seniority", "department",
    "role_overview", "salary_currency", "salary_interval",
)
ARRAY_FIELDS = (
    "locations", "responsibilities", "qualifications", "job_conditions",
    "compensation", "benefits", "other_relevant_information",
)
BASE_PAY_TYPES = frozenset(("base_salary", "hourly_rate"))
MAX_ISSUES = 100


@dataclass(frozen=True)
class ValidationIssue:
    """A fixed rule code and schema path, with no copied source content."""

    code: str
    path: str


class JobPostingAnalysisContentValidationError(JobPostingAnalysisValidationError):
    """An extraction violates a deterministically checkable content rule."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = tuple(issues)
        # Only fixed codes and paths constructed below may enter this error text.
        shown = "; ".join(f"{issue.code} at {issue.path}" for issue in self.issues[:8])
        suffix = "; additional issues omitted" if len(self.issues) > 8 else ""
        super().__init__(f"Local content validation failed: {shown}{suffix}.")


def validate_analysis_content(payload: dict[str, Any], *, posting: dict[str, Any]) -> None:
    """Validate already schema-checked output against its exact supplied posting.

    Evidence matching is exact after JSON decoding. It does not establish that a
    quote supports a paraphrase, classification or requirement level. No changes
    are made to either input, and no source data appears in failure messages.
    """
    issues: list[ValidationIssue] = []

    def reject(code: str, path: str) -> None:
        if len(issues) < MAX_ISSUES:
            issues.append(ValidationIssue(code, path))

    def check_evidence(evidence: list[dict[str, str]], path: str) -> None:
        for index, entry in enumerate(evidence):
            entry_path = f"{path}/{index}"
            quote = entry["quote"]
            if not quote.strip():
                reject("empty_evidence_quote", f"{entry_path}/quote")
                continue
            source_field = entry["source_field"]
            if source_field not in posting:
                reject("unknown_evidence_source", f"{entry_path}/source_field")
                continue
            source = posting[source_field]
            if isinstance(source, str):
                if quote not in source:
                    reject("evidence_quote_not_in_source", f"{entry_path}/quote")
            elif isinstance(source, (bool, int, float)):
                try:
                    representation = json.dumps(source, ensure_ascii=False, allow_nan=False)
                except (ValueError, OverflowError):
                    reject("unsupported_evidence_source", f"{entry_path}/source_field")
                    continue
                if quote != representation:
                    reject("evidence_scalar_not_exact", f"{entry_path}/quote")
            else:
                reject("unsupported_evidence_source", f"{entry_path}/source_field")

    def check_value(item: dict[str, Any], path: str, *, nullable: bool) -> None:
        value = item["value"]
        evidence = item["evidence"]
        if value is None and nullable:
            if evidence:
                reject("null_value_has_evidence", f"{path}/evidence")
        else:
            if not isinstance(value, str) or not value.strip():
                reject("empty_value", f"{path}/value")
            if not evidence:
                reject("missing_evidence", f"{path}/evidence")
        check_evidence(evidence, f"{path}/evidence")

    for field in SCALAR_FIELDS:
        check_value(payload[field], f"/{field}", nullable=True)
    for field in ARRAY_FIELDS:
        for index, item in enumerate(payload[field]):
            check_value(item, f"/{field}/{index}", nullable=False)

    for field in COPIED_METADATA_FIELDS:
        item = payload[field]
        original = posting.get(field)
        path = f"/{field}"
        if original is None or original == "":
            if item["value"] is not None or item["evidence"]:
                reject("metadata_absent_not_null", path)
            continue
        if not isinstance(original, str):
            reject("metadata_source_not_string", path)
            continue
        if item["value"] != original:
            reject("metadata_not_exact_copy", f"{path}/value")
        if item["evidence"] != [{"source_field": field, "quote": original}]:
            reject("metadata_evidence_not_exact", f"{path}/evidence")

    for index, item in enumerate(payload["qualifications"]):
        categories = item["categories"]
        if not categories:
            reject("qualification_categories_empty", f"/qualifications/{index}/categories")
        elif len(set(categories)) != len(categories):
            reject("qualification_categories_duplicate", f"/qualifications/{index}/categories")

    for index, item in enumerate(payload["compensation"]):
        minimum, maximum = item["minimum"], item["maximum"]
        path = f"/compensation/{index}"
        for attribute in ("currency", "applies_to"):
            value = item[attribute]
            if value is not None and not value.strip():
                reject("empty_compensation_attribute", f"{path}/{attribute}")
        for name, amount in (("minimum", minimum), ("maximum", maximum)):
            if amount is not None and amount < 0:
                reject("negative_monetary_amount", f"{path}/{name}")
        if minimum is not None and maximum is not None and minimum > maximum:
            reject("monetary_bounds_reversed", path)

    base_pay = [item for item in payload["compensation"] if item["type"] in BASE_PAY_TYPES]
    for field, attribute in (("salary_currency", "currency"), ("salary_interval", "interval")):
        value = payload[field]["value"]
        if value is None:
            continue
        def equivalent(item_value: Any) -> bool:
            if attribute == "currency" and isinstance(item_value, str):
                return item_value.casefold() == value.casefold()
            return item_value == value

        if base_pay and any(not equivalent(item[attribute]) for item in base_pay):
            reject("base_summary_inconsistent", f"/{field}/value")

    if issues:
        raise JobPostingAnalysisContentValidationError(tuple(issues))
