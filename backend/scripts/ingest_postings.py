"""Fetch every board in data/companies.yaml and store the postings in the database.

Run from backend/ once a day:
    python -m scripts.ingest_postings
    python -m scripts.ingest_postings --source ashby
    python -m scripts.ingest_postings --company stripe --company openai

Exits with status 1 only when every board failed, so one broken board does not fail a scheduled run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.postings.ashby import AshbyAdapter
from app.services.postings.base import create_http_client
from app.services.postings.companies import Company, load_companies
from app.services.postings.greenhouse import GreenhouseAdapter
from app.services.postings.ingest import REQUEST_DELAY_SECONDS, BoardResult, ingest
from app.services.postings.lever import LeverAdapter


def select_companies(companies: list[Company], sources: list[str], names: list[str]) -> list[Company]:
    wanted = {name.lower() for name in names}
    selected = []
    for company in companies:
        boards = [
            board
            for board in company.boards
            if (not sources or board.source in sources)
            and (not wanted or company.name.lower() in wanted or board.slug.lower() in wanted)
        ]
        if boards:
            selected.append(company.model_copy(update={"boards": boards}))
    return selected


def print_result(result: BoardResult) -> None:
    label = f"{result.company} ({result.source}/{result.slug})"
    if result.status == "success":
        print(
            f"ok    {label}: {result.fetched} open, {result.inserted} new, {result.updated} changed, "
            f"{result.reopened} reopened, {result.closed} closed"
        )
    else:
        print(f"error {label}: {result.error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", action="append", choices=["greenhouse", "ashby", "lever"], default=[])
    parser.add_argument("--company", action="append", default=[], help="company name or board slug")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS, help="seconds between requests")
    args = parser.parse_args()

    companies = select_companies(load_companies(), args.source, args.company)
    if not companies:
        print("No boards match the given filters.", file=sys.stderr)
        return 1

    with create_http_client() as client, SessionLocal() as session:
        adapters = {
            "greenhouse": GreenhouseAdapter(client),
            "ashby": AshbyAdapter(client),
            "lever": LeverAdapter(client),
        }
        results = ingest(session, companies, adapters, delay_seconds=args.delay, on_result=print_result)

    failed = sum(result.status != "success" for result in results)
    print(
        f"\n{len(results) - failed}/{len(results)} boards succeeded: "
        f"{sum(r.fetched for r in results)} open postings, {sum(r.inserted for r in results)} new, "
        f"{sum(r.closed for r in results)} closed."
    )
    return 1 if failed == len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
