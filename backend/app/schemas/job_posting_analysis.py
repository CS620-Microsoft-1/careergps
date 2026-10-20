"""HTTP models and validation for the frozen version 10 JD output contract."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, ValidationError
from pydantic import BaseModel, ConfigDict, StrictBool


class JobPostingAnalysisValidationError(ValueError):
    """An Agent result cannot be safely accepted as this posting's analysis."""


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    path = Path(__file__).with_name("job_posting_analysis_v10.json")
    response_format = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(response_format["schema"])


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number.")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number.")
    return number


def validate_analysis_response(
    output_text: str, *, job_posting_id: str
) -> dict[str, Any]:
    """Check JSON, schema and identity only; evidence and semantics are not verified."""
    if not isinstance(output_text, str) or not output_text.strip():
        raise JobPostingAnalysisValidationError("The job analysis Agent returned no JSON.")
    try:
        payload = json.loads(
            output_text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError):
        raise JobPostingAnalysisValidationError(
            "The job analysis Agent returned invalid JSON."
        ) from None

    try:
        _validator().validate(payload)
    except (ValidationError, RecursionError):
        # jsonschema's exception text can contain the full JD or generated result.
        raise JobPostingAnalysisValidationError(
            "The job analysis Agent response does not match the version 10 schema."
        ) from None
    if payload["id"]["value"] != job_posting_id:
        raise JobPostingAnalysisValidationError(
            "The job analysis Agent response belongs to a different posting."
        )
    return payload


class JobPostingAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: StrictBool = False


class JobPostingAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_posting_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    structured_data: dict[str, Any] | None
    error_message: str | None
