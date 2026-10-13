from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx2

from app.schemas.market import NormalizedPosting
from app.services.postings.base import BoardFetchError, clean, country_code, get_json
from app.services.postings.text import html_to_text, normalize_text

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"

_WORKPLACE_TYPES = {"Remote": "remote", "Hybrid": "hybrid", "OnSite": "onsite"}
_EMPLOYMENT_TYPES = {
    "FullTime": "full_time",
    "PartTime": "part_time",
    "Intern": "intern",
    "Contract": "contract",
    "Temporary": "temporary",
}
_SALARY_INTERVALS = {
    "1 YEAR": "year",
    "1 MONTH": "month",
    "1 WEEK": "week",
    "1 DAY": "day",
    "1 HOUR": "hour",
}


class AshbyAdapter:
    source = "ashby"

    def __init__(self, client: httpx2.Client) -> None:
        self.client = client

    def fetch(self, slug: str) -> list[NormalizedPosting]:
        payload = get_json(self.client, f"{BASE_URL}/{slug}", params={"includeCompensation": "true"})
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise BoardFetchError(f"Ashby board {slug} returned no job list.")
        return [parse_job(job) for job in jobs if job.get("isListed", True)]


def _salary(compensation: dict[str, Any] | None) -> dict[str, Any]:
    for component in (compensation or {}).get("summaryComponents") or []:
        if component.get("compensationType") != "Salary":
            continue
        interval = _SALARY_INTERVALS.get(component.get("interval") or "")
        minimum, maximum = component.get("minValue"), component.get("maxValue")
        if interval and (minimum is not None or maximum is not None):
            return {
                "salary_min": int(minimum) if minimum is not None else None,
                "salary_max": int(maximum) if maximum is not None else None,
                "salary_currency": clean(component.get("currencyCode")),
                "salary_interval": interval,
            }
    return {"salary_min": None, "salary_max": None, "salary_currency": None, "salary_interval": None}


def parse_job(job: dict[str, Any]) -> NormalizedPosting:
    address = ((job.get("address") or {}).get("postalAddress")) or {}
    workplace_type = _WORKPLACE_TYPES.get(job.get("workplaceType") or "")
    if workplace_type is None and job.get("isRemote") is True:
        workplace_type = "remote"
    published = clean(job.get("publishedAt"))
    return NormalizedPosting(
        source="ashby",
        external_id=str(job["id"]),
        title=job["title"].strip(),
        location=clean(job.get("location")),
        country=country_code(address.get("addressCountry")),
        workplace_type=workplace_type,
        department=clean(job.get("department")) or clean(job.get("team")),
        employment_type=_EMPLOYMENT_TYPES.get(job.get("employmentType") or ""),
        description_text=normalize_text(job.get("descriptionPlain"))
        or html_to_text(job.get("descriptionHtml")),
        **_salary(job.get("compensation")),
        url=job["jobUrl"],
        published_at=datetime.fromisoformat(published) if published else None,
    )
