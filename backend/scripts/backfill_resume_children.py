"""Rebuild the résumé child tables (experiences, educations, projects, achievements, skills) from
resumes.confirmed_data for every stored résumé.

New résumés get their child rows when they are saved; run this once for résumés saved before that, and
again whenever the rules in app/services/resume_children.py change. Safe to re-run. Run from backend/:
    python -m scripts.backfill_resume_children --dry-run
    python -m scripts.backfill_resume_children

--dry-run still sends the rows to the database, so its constraints are checked, then rolls back.
Each résumé is its own transaction. Only ids and counts are printed: résumés hold personal data.
Exits with status 1 if any résumé failed.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Resume
from app.services.resume_children import CHILD_MODELS, rebuild_children


@dataclass
class ResumeResult:
    resume_id: uuid.UUID
    counts: Counter[str] = field(default_factory=Counter)
    error: str | None = None


def describe_error(error: Exception) -> str:
    """The error type and, for database errors, the constraint; never the message, which can quote résumé values."""
    constraint = getattr(getattr(getattr(error, "orig", None), "diag", None), "constraint_name", None)
    return f"{type(error).__name__} ({constraint})" if constraint else type(error).__name__


def backfill(session: Session, *, dry_run: bool, on_result=None) -> list[ResumeResult]:
    resume_ids = list(session.scalars(select(Resume.id).order_by(Resume.created_at)))
    results = []
    for resume_id in resume_ids:
        result = ResumeResult(resume_id)
        try:
            rows = rebuild_children(session, session.get(Resume, resume_id))
            session.flush()  # the database checks every row here, inside the try
            result.counts.update(row.__tablename__ for row in rows)
        except Exception as error:
            session.rollback()
            result.error = describe_error(error)
        else:
            if dry_run:
                session.rollback()
            else:
                session.commit()
        results.append(result)
        if on_result:
            on_result(result)
    return results


def print_result(result: ResumeResult) -> None:
    if result.error:
        print(f"error {result.resume_id}: {result.error}")
    else:
        counts = ", ".join(f"{result.counts[model.__tablename__]} {model.__tablename__}" for model in CHILD_MODELS)
        print(f"ok    {result.resume_id}: {counts}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="check every row, then roll back")
    args = parser.parse_args()

    with SessionLocal() as session:
        results = backfill(session, dry_run=args.dry_run, on_result=print_result)

    failed = sum(result.error is not None for result in results)
    total = sum((result.counts for result in results), Counter())
    print(
        f"\n{len(results) - failed}/{len(results)} résumés {'checked' if args.dry_run else 'rebuilt'}: "
        + ", ".join(f"{total[model.__tablename__]} {model.__tablename__}" for model in CHILD_MODELS)
        + (" (dry run, nothing saved)" if args.dry_run else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
