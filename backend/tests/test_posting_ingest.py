import os
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.job_posting import IngestRun, JobPosting
from app.schemas.market import NormalizedPosting
from app.services.postings.base import BoardFetchError
from app.services.postings.companies import Board, Company
from app.services.postings.ingest import content_hash, ingest

START = datetime(2026, 10, 1, 12, tzinfo=UTC)


def posting(external_id: str, title: str = "Software Engineer", description: str = "Python") -> NormalizedPosting:
    return NormalizedPosting(
        source="greenhouse",
        external_id=external_id,
        title=title,
        location="New York, NY",
        country=None,
        workplace_type=None,
        department="Engineering",
        employment_type=None,
        description_text=description,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_interval=None,
        url=f"https://example.test/{external_id}",
        published_at=None,
    )


class FakeAdapter:
    source = "greenhouse"

    def __init__(self) -> None:
        self.boards: dict[str, list[NormalizedPosting] | Exception] = {}

    def fetch(self, slug: str) -> list[NormalizedPosting]:
        value = self.boards[slug]
        if isinstance(value, Exception):
            raise value
        return value


class IngestTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        # Only the ingest tables: others use Postgres-only types (ARRAY, JSONB) that SQLite can't create.
        Base.metadata.create_all(engine, tables=[JobPosting.__table__, IngestRun.__table__])
        self.session = Session(engine)
        self.adapter = FakeAdapter()
        self.day = 0
        self.sleeps: list[float] = []
        self.company = Company(name="Example", tier="other", boards=[Board(source="greenhouse", slug="example")])

    def tearDown(self) -> None:
        self.session.close()

    def run_ingest(self, companies: list[Company] | None = None):
        now = START + timedelta(days=self.day)
        self.day += 1
        return ingest(
            self.session,
            companies or [self.company],
            {"greenhouse": self.adapter},
            clock=lambda: now,
            sleep=self.sleeps.append,
        )

    def postings(self) -> dict[str, JobPosting]:
        return {row.external_id: row for row in self.session.scalars(select(JobPosting))}

    def test_first_run_inserts_postings(self) -> None:
        self.adapter.boards["example"] = [posting("1"), posting("2")]

        (result,) = self.run_ingest()

        self.assertEqual(("success", 2, 2), (result.status, result.fetched, result.inserted))
        rows = self.postings()
        self.assertEqual({"1", "2"}, set(rows))
        self.assertEqual("Example", rows["1"].company_name)
        self.assertEqual("other", rows["1"].company_tier)
        self.assertEqual(rows["1"].first_seen_at, rows["1"].last_seen_at)
        self.assertEqual(content_hash(posting("1")), rows["1"].content_hash)

    def test_unchanged_posting_only_updates_last_seen(self) -> None:
        self.adapter.boards["example"] = [posting("1")]
        self.run_ingest()
        (result,) = self.run_ingest()

        self.assertEqual((0, 0, 0), (result.inserted, result.updated, result.closed))
        row = self.postings()["1"]
        self.assertEqual(timedelta(days=1), row.last_seen_at - row.first_seen_at)

    def test_changed_posting_is_updated(self) -> None:
        self.adapter.boards["example"] = [posting("1")]
        self.run_ingest()
        self.adapter.boards["example"] = [posting("1", description="Python and Go")]
        (result,) = self.run_ingest()

        self.assertEqual(1, result.updated)
        self.assertEqual("Python and Go", self.postings()["1"].description_text)

    def test_missing_posting_is_closed_and_reopened_when_listed_again(self) -> None:
        self.adapter.boards["example"] = [posting("1"), posting("2")]
        self.run_ingest()
        self.adapter.boards["example"] = [posting("1")]
        (closed_run,) = self.run_ingest()

        self.assertEqual(1, closed_run.closed)
        self.assertIsNotNone(self.postings()["2"].closed_at)
        self.assertIsNone(self.postings()["1"].closed_at)

        self.adapter.boards["example"] = [posting("1"), posting("2")]
        (reopened_run,) = self.run_ingest()

        self.assertEqual((1, 0), (reopened_run.reopened, reopened_run.inserted))
        self.assertIsNone(self.postings()["2"].closed_at)

    def test_empty_board_closes_all_postings(self) -> None:
        self.adapter.boards["example"] = [posting("1")]
        self.run_ingest()
        self.adapter.boards["example"] = []
        (result,) = self.run_ingest()

        self.assertEqual(1, result.closed)

    def test_failed_board_is_recorded_and_does_not_stop_the_run(self) -> None:
        self.adapter.boards["example"] = [posting("1")]
        self.run_ingest()
        broken = Company(name="Broken", tier="other", boards=[Board(source="greenhouse", slug="broken")])
        self.adapter.boards["broken"] = BoardFetchError("HTTP 500")

        failed, succeeded = self.run_ingest([broken, self.company])

        self.assertEqual(("failed", "HTTP 500"), (failed.status, failed.error))
        self.assertEqual("success", succeeded.status)
        self.assertIsNone(self.postings()["1"].closed_at, "a failed fetch must not close postings")
        runs = self.session.scalars(select(IngestRun).order_by(IngestRun.started_at)).all()
        self.assertEqual(["success", "failed", "success"], [run.status for run in runs])
        self.assertEqual([1.0], self.sleeps)

    def test_long_values_and_nul_characters_are_cleaned(self) -> None:
        self.adapter.boards["example"] = [posting("1", title="T" * 600, description="a\x00b")]
        self.run_ingest()

        row = self.postings()["1"]
        self.assertEqual(500, len(row.title))
        self.assertEqual("ab", row.description_text)


if __name__ == "__main__":
    unittest.main()
