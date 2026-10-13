from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx2

from app.schemas.market import NormalizedPosting
from app.services.postings.base import BoardFetchError, clean, country_code, get_json
from app.services.postings.text import html_to_text, normalize_text

BASE_URL = "https://api.lever.co/v0/postings"

_WORKPLACE_TYPES = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite"}
_INTERVAL_WORDS = ("year", "month", "week", "day", "hour")


class LeverAdapter:
    source = "lever"

    def __init__(self, client: httpx2.Client) -> None:
        self.client = client

    def fetch(self, slug: str) -> list[NormalizedPosting]:
        payload = get_json(self.client, f"{BASE_URL}/{slug}", params={"mode": "json"})
        if not isinstance(payload, list):
            raise BoardFetchError(f"Lever board {slug} returned no job list.")
        return [parse_job(job) for job in payload]


def _employment_type(commitment: str | None) -> str | None:
    value = (commitment or "").lower()
    if "intern" in value:
        return "intern"
    if "part" in value:
        return "part_time"
    if "full" in value:
        return "full_time"
    if "contract" in value:
        return "contract"
    if "temp" in value or "fixed" in value:
        return "temporary"
    return None


def _salary(salary_range: dict[str, Any] | None) -> dict[str, Any]:
    salary_range = salary_range or {}
    interval_text = (salary_range.get("interval") or "").lower()
    interval = next((word for word in _INTERVAL_WORDS if word in interval_text), None)
    minimum, maximum = salary_range.get("min"), salary_range.get("max")
    if interval is None or (minimum is None and maximum is None):
        return {"salary_min": None, "salary_max": None, "salary_currency": None, "salary_interval": None}
    return {
        "salary_min": int(minimum) if minimum is not None else None,
        "salary_max": int(maximum) if maximum is not None else None,
        "salary_currency": clean(salary_range.get("currency")),
        "salary_interval": interval,
    }


def _description(job: dict[str, Any]) -> str:
    sections = [normalize_text(job.get("descriptionPlain"))]
    for item in job.get("lists") or []:
        heading = (item.get("text") or "").strip()
        body = html_to_text(item.get("content"))
        sections.append("\n".join(part for part in (heading, body) if part))
    sections.append(normalize_text(job.get("additionalPlain")))
    return "\n\n".join(section for section in sections if section)


def parse_job(job: dict[str, Any]) -> NormalizedPosting:
    categories = job.get("categories") or {}
    created_at = job.get("createdAt")
    return NormalizedPosting(
        source="lever",
        external_id=str(job["id"]),
        title=job["text"].strip(),
        location=clean(categories.get("location")),
        country=country_code(job.get("country")),
        workplace_type=_WORKPLACE_TYPES.get((job.get("workplaceType") or "").lower()),
        department=clean(categories.get("department")) or clean(categories.get("team")),
        employment_type=_employment_type(categories.get("commitment")),
        description_text=_description(job),
        **_salary(job.get("salaryRange")),
        url=job["hostedUrl"],
        published_at=datetime.fromtimestamp(int(created_at) / 1000, tz=UTC) if created_at else None,
    )
