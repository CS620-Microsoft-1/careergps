from __future__ import annotations

import json
import re
from copy import deepcopy
from contextlib import ExitStack
from typing import Any

from pydantic import ValidationError

from app.schemas.resume import ResumeClassification

class FoundryAgentError(RuntimeError):
    """A sanitized Agent failure that never includes résumé content."""


class ClassificationValidationError(ValueError):
    """The existing Agent did not return supported classified-resume JSON."""


_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE = re.compile(r"^\+?[\d().\s-]{7,}$")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_DATE_RANGE = re.compile(r"^\s*(.+?)(?:\s+-\s+|\s*[–—]\s*|\s+to\s+)(.+?)\s*$", re.I)
_ISO_MONTH = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])$")
_NUMERIC_MONTH = re.compile(r"^(0?[1-9]|1[0-2])[/.-]((?:19|20)\d{2})$")
_TEXT_MONTH = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(?:\d{1,2},?\s+)?((?:19|20)\d{2})\b",
    re.I,
)
_SEASON_YEAR = re.compile(r"\b(?:spring|summer|fall|autumn|winter)\s+((?:19|20)\d{2})\b", re.I)
_CERTIFICATE_LINE = re.compile(
    r"^\s*(?:minor(?:s)?\s*/\s*)?cert(?:ificate|ification)s?\s*:\s*(.+?)\s*$",
    re.I,
)
_DEGREE_MAJOR = re.compile(
    r"^(?P<degree>(?:(?:bachelor|master|doctor|associate)(?:'s)?(?:\s+of\s+.+?)?|"
    r"(?:[bma]\.[a-z]\.?|ph\.?d\.?)))\s+in\s+(?P<major>.+)$",
    re.I,
)
_MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_DATED_SECTIONS = (
    "education",
    "work_experience",
    "research_experience",
    "leadership_activities",
)
_LIST_CONTENT_SECTIONS = (
    "education",
    "work_experience",
    "research_experience",
    "projects",
    "publications",
    "awards_honors",
    "certifications",
    "leadership_activities",
)


def parse_json_response(output_text: str) -> dict[str, Any]:
    if not isinstance(output_text, str) or not output_text.strip():
        raise ClassificationValidationError("The Agent returned an empty response.")
    candidate = output_text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.I | re.S)
    if fence:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ClassificationValidationError("The Agent response contains no JSON object.")
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as error:
            raise ClassificationValidationError("The Agent response contains invalid JSON.") from error
    if not isinstance(parsed, dict):
        raise ClassificationValidationError("The Agent response must be a JSON object.")
    return parsed


def _split_date_range(value: str) -> tuple[str, str] | None:
    match = _DATE_RANGE.fullmatch(value)
    if not match:
        return None
    start, end = (part.strip() for part in match.groups())
    end_years = _YEAR.findall(end)
    if not _YEAR.search(start) and len(end_years) == 1:
        separator = ", " if re.search(r"\b\d{1,2}$", start) else " "
        start = f"{start}{separator}{end_years[0]}"
    return start, end


def _normalize_month_year(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    if cleaned.lower() in {"present", "current", "now"}:
        return "Present"
    if _ISO_MONTH.fullmatch(cleaned) or re.fullmatch(r"(?:19|20)\d{2}", cleaned):
        return cleaned
    if match := _NUMERIC_MONTH.fullmatch(cleaned):
        month, year = match.groups()
        return f"{year}-{int(month):02d}"
    if match := _TEXT_MONTH.search(cleaned):
        month_name, year = match.groups()
        return f"{year}-{_MONTH_NUMBERS[month_name[:3].lower()]:02d}"
    if match := _SEASON_YEAR.search(cleaned):
        return match.group(1)
    return cleaned


def _format_us_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return value.strip()
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _normalize_agent_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize deterministic formatting issues before enforcing the strict contract."""
    candidate = deepcopy(payload)
    personal = candidate.get("personal_information")
    if isinstance(personal, dict):
        raw_emails = personal.get("emails", [])
        emails = raw_emails if isinstance(raw_emails, list) else [raw_emails]
        legacy_email = personal.pop("email", None)
        if legacy_email:
            emails.append(legacy_email)

        raw_phones = personal.get("phones", [])
        phones = raw_phones if isinstance(raw_phones, list) else [raw_phones]
        legacy_phone = personal.pop("phone", None)
        if legacy_phone:
            phones.append(legacy_phone)

        other_contacts = personal.pop("other_contacts", [])
        if isinstance(other_contacts, list):
            for contact in other_contacts:
                if isinstance(contact, str) and _EMAIL.fullmatch(contact.strip()):
                    emails.append(contact.strip())
                elif isinstance(contact, str) and _PHONE.fullmatch(contact.strip()):
                    phones.append(contact.strip())

        personal["emails"] = list(
            dict.fromkeys(email.strip() for email in emails if isinstance(email, str) and email.strip())
        )
        personal["phones"] = list(
            dict.fromkeys(
                _format_us_phone(phone) for phone in phones if isinstance(phone, str) and phone.strip()
            )
        )

    for section in _DATED_SECTIONS:
        entries = candidate.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            start_date = entry.get("start_date")
            if (
                entry.get("end_date") in (None, "")
                and isinstance(start_date, str)
                and (date_range := _split_date_range(start_date))
            ):
                entry["start_date"], entry["end_date"] = date_range
            for field in ("start_date", "end_date"):
                value = entry.get(field)
                if isinstance(value, str):
                    entry[field] = _normalize_month_year(value)

    for section in _LIST_CONTENT_SECTIONS:
        entries = candidate.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content")
            if content is None:
                entry["content"] = []
            elif isinstance(content, str):
                entry["content"] = [content] if content.strip() else []

    education = candidate.get("education")
    if isinstance(education, list):
        for entry in education:
            if not isinstance(entry, dict):
                continue
            legacy_major = entry.pop("field_of_study", None)
            if not entry.get("major") and legacy_major:
                entry["major"] = legacy_major
            degree = entry.get("degree")
            if not entry.get("major") and isinstance(degree, str):
                if match := _DEGREE_MAJOR.fullmatch(degree.strip()):
                    entry["degree"] = match.group("degree")
                    entry["major"] = match.group("major")

    certifications = candidate.get("certifications")
    if isinstance(education, list) and isinstance(certifications, list):
        existing_names = {
            item.get("name", "").strip().casefold()
            for item in certifications
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        for entry in education:
            if not isinstance(entry, dict) or not isinstance(entry.get("content"), list):
                continue
            retained_content: list[Any] = []
            for line in entry["content"]:
                match = _CERTIFICATE_LINE.fullmatch(line) if isinstance(line, str) else None
                if not match:
                    retained_content.append(line)
                    continue
                for name in (part.strip() for part in match.group(1).split(";")):
                    if not name or name.casefold() in existing_names:
                        continue
                    certifications.append(
                        {
                            "name": name,
                            "issuer": None,
                            "date": None,
                            "url": None,
                            "content": [],
                        }
                    )
                    existing_names.add(name.casefold())
            entry["content"] = retained_content
    return candidate


def validate_classification(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload
    if len(candidate) == 1:
        only_key, only_value = next(iter(candidate.items()))
        normalized = re.sub(r"[^a-z0-9]+", "", str(only_key).lower())
        if normalized in {"resume", "classifiedresume", "classification"} and isinstance(only_value, dict):
            candidate = only_value
    candidate = _normalize_agent_output(candidate)
    try:
        return ResumeClassification.model_validate(candidate).model_dump()
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_url=False)[:8]
        )
        raise ClassificationValidationError(details) from error


class FoundryResumeAgentService:
    def __init__(
        self,
        endpoint: str | None,
        agent_name: str | None,
        *,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.endpoint = endpoint or ""
        self.agent_name = agent_name or ""
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def classify(self, extracted_resume_text: str) -> dict[str, Any]:
        if not self.endpoint or not self.agent_name:
            raise FoundryAgentError("The Foundry Agent is not configured on the backend.")
        if not extracted_resume_text.strip():
            raise ClassificationValidationError("No résumé text was available for classification.")

        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError as error:
            raise FoundryAgentError("The Foundry SDK dependencies are not installed.") from error

        try:
            with ExitStack() as stack:
                credential = stack.enter_context(DefaultAzureCredential())
                project = stack.enter_context(
                    AIProjectClient(endpoint=self.endpoint, credential=credential, allow_preview=True)
                )
                client = stack.enter_context(
                    project.get_openai_client(
                        agent_name=self.agent_name,
                        timeout=self.timeout_seconds,
                        max_retries=self.max_retries,
                    )
                )
                conversation = client.conversations.create()
                try:
                    response = client.responses.create(
                        conversation=conversation.id,
                        input=[{"role": "user", "content": extracted_resume_text}],
                    )
                    return validate_classification(parse_json_response(response.output_text))
                finally:
                    try:
                        client.conversations.delete(conversation_id=conversation.id)
                    except Exception:
                        # Cleanup must not replace the result or expose résumé data.
                        pass
        except ClassificationValidationError:
            raise
        except Exception as error:
            name = type(error).__name__
            status = getattr(error, "status_code", None)
            if status in (401, 403) or "Authentication" in name or "Credential" in name:
                message = "Azure authentication failed. Run 'az login' and verify Foundry permissions."
            elif status == 429 or "RateLimit" in name:
                message = "The Foundry Agent rate limit was reached. Try again shortly."
            elif "Timeout" in name:
                message = "The Foundry Agent request timed out."
            else:
                message = f"The Foundry Agent request failed ({name})."
            raise FoundryAgentError(message) from error
