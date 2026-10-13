from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx2

from app.schemas.market import NormalizedPosting
from app.services.postings.base import BoardFetchError, clean, get_json
from app.services.postings.text import html_to_text, unescape_html

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseAdapter:
    source = "greenhouse"

    def __init__(self, client: httpx2.Client) -> None:
        self.client = client

    def fetch(self, slug: str) -> list[NormalizedPosting]:
        payload = get_json(self.client, f"{BASE_URL}/{slug}/jobs", params={"content": "true"})
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise BoardFetchError(f"Greenhouse board {slug} returned no job list.")
        return [parse_job(job) for job in jobs]


def parse_job(job: dict[str, Any]) -> NormalizedPosting:
    departments = job.get("departments") or []
    published = clean(job.get("first_published"))
    return NormalizedPosting(
        source="greenhouse",
        external_id=str(job["id"]),
        title=job["title"].strip(),
        location=clean((job.get("location") or {}).get("name")),
        # Greenhouse locations are free text; country and workplace type are parsed later.
        country=None,
        workplace_type=None,
        department=clean(departments[0].get("name")) if departments else None,
        employment_type=None,
        description_text=html_to_text(unescape_html(job.get("content"))),
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_interval=None,
        url=job["absolute_url"],
        published_at=datetime.fromisoformat(published) if published else None,
    )
