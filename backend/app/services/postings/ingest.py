from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.job_posting import IngestRun, JobPosting
from app.schemas.market import NormalizedPosting
from app.services.postings.base import BoardFetchError, BoardNotFoundError, PostingSourceAdapter
from app.services.postings.companies import Board, Company

REQUEST_DELAY_SECONDS = 1.0

# Column lengths from the job_postings table; longer values are truncated instead of failing the run.
_MAX_LENGTHS = {"title": 500, "location": 500, "department": 255}


@dataclass
class BoardResult:
    company: str
    source: str
    slug: str
    status: str = "success"
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    reopened: int = 0
    closed: int = 0
    error: str | None = None


def content_hash(posting: NormalizedPosting) -> str:
    payload = json.dumps(posting.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _columns(posting: NormalizedPosting) -> dict:
    values = posting.model_dump(exclude={"source", "external_id"})
    for key, value in values.items():
        if isinstance(value, str):
            # Postgres text cannot store NUL characters.
            value = value.replace("\x00", "")
            if key in _MAX_LENGTHS:
                value = value[: _MAX_LENGTHS[key]]
            values[key] = value
    return values


def sync_board(
    session: Session,
    company: Company,
    board: Board,
    postings: list[NormalizedPosting],
    now: datetime,
    result: BoardResult,
) -> None:
    """Upsert one board's open postings and close the ones that are no longer listed."""
    fetched = {posting.external_id: posting for posting in postings}
    result.fetched = len(fetched)
    conditions = [JobPosting.company_slug == board.slug]
    if fetched:
        conditions.append(JobPosting.external_id.in_(fetched))
    existing = {
        row.external_id: row
        for row in session.scalars(
            select(JobPosting).where(JobPosting.source == board.source, or_(*conditions))
        )
    }

    for external_id, posting in fetched.items():
        digest = content_hash(posting)
        row = existing.get(external_id)
        if row is None:
            session.add(
                JobPosting(
                    source=board.source,
                    external_id=external_id,
                    company_slug=board.slug,
                    company_name=company.name,
                    company_tier=company.tier,
                    first_seen_at=now,
                    last_seen_at=now,
                    content_hash=digest,
                    **_columns(posting),
                )
            )
            result.inserted += 1
            continue

        row.last_seen_at = now
        row.company_slug, row.company_name, row.company_tier = board.slug, company.name, company.tier
        if row.closed_at is not None:
            row.closed_at = None
            result.reopened += 1
        if row.content_hash != digest:
            for key, value in _columns(posting).items():
                setattr(row, key, value)
            row.content_hash = digest
            result.updated += 1

    for external_id, row in existing.items():
        if external_id not in fetched and row.company_slug == board.slug and row.closed_at is None:
            row.closed_at = now
            result.closed += 1


def ingest(
    session: Session,
    companies: Iterable[Company],
    adapters: Mapping[str, PostingSourceAdapter],
    *,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    on_result: Callable[[BoardResult], None] | None = None,
) -> list[BoardResult]:
    """Fetch and store every board, one transaction per board, so one failure never stops the run."""
    results = []
    first_request = True
    for company in companies:
        for board in company.boards:
            if not first_request:
                sleep(delay_seconds)
            first_request = False

            started_at = clock()
            result = BoardResult(company=company.name, source=board.source, slug=board.slug)
            try:
                postings = adapters[board.source].fetch(board.slug)
                sync_board(session, company, board, postings, started_at, result)
                # Send the writes now, so a database error (e.g. a salary too big for INTEGER) fails
                # only this board. Autoflush is off, so without this they would first run at commit.
                session.flush()
            except Exception as error:
                session.rollback()
                result = BoardResult(company=company.name, source=board.source, slug=board.slug)
                result.status = "failed"
                if isinstance(error, BoardNotFoundError):
                    result.error = "Board not found."
                elif isinstance(error, BoardFetchError):
                    result.error = str(error)
                else:
                    result.error = f"Unexpected {type(error).__name__}: {error}"[:1000]

            session.add(
                IngestRun(
                    source=board.source,
                    company_slug=board.slug,
                    started_at=started_at,
                    finished_at=clock(),
                    status=result.status,
                    fetched=result.fetched,
                    inserted=result.inserted,
                    updated=result.updated,
                    reopened=result.reopened,
                    closed=result.closed,
                    error=result.error,
                )
            )
            session.commit()
            results.append(result)
            if on_result:
                on_result(result)
    return results
