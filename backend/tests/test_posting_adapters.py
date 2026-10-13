import json
import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "postings"
sys.path.insert(0, str(BACKEND_ROOT))

import httpx2

from app.services.postings.ashby import AshbyAdapter
from app.services.postings.base import BoardFetchError, BoardNotFoundError, create_http_client
from app.services.postings.greenhouse import GreenhouseAdapter
from app.services.postings.lever import LeverAdapter
from app.services.postings.text import html_to_text


def fixture_client(name: str, requests: list[httpx2.Request] | None = None) -> httpx2.Client:
    body = (FIXTURES / f"{name}.json").read_bytes()

    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        return httpx2.Response(200, content=body, headers={"Content-Type": "application/json"})

    return create_http_client(httpx2.MockTransport(handler))


def status_client(status_code: int, content: bytes = b"") -> httpx2.Client:
    return create_http_client(httpx2.MockTransport(lambda _: httpx2.Response(status_code, content=content)))


class HtmlToTextTests(unittest.TestCase):
    def test_keeps_paragraphs_and_list_items(self) -> None:
        text = html_to_text("<p>Intro&nbsp;text</p><ul><li>Python</li><li>SQL</li></ul><script>x()</script>")
        self.assertEqual("Intro text\n\n- Python\n- SQL", text)

    def test_empty_input(self) -> None:
        self.assertEqual("", html_to_text(None))
        self.assertEqual("", html_to_text(""))


class GreenhouseAdapterTests(unittest.TestCase):
    def test_fetch_requests_content_and_parses_jobs(self) -> None:
        requests: list[httpx2.Request] = []
        postings = GreenhouseAdapter(fixture_client("greenhouse", requests)).fetch("examplepay")

        self.assertEqual("/v1/boards/examplepay/jobs", requests[0].url.path)
        self.assertEqual("true", requests[0].url.params["content"])
        self.assertIn("CareerGPS", requests[0].headers["User-Agent"])
        self.assertEqual(2, len(postings))

        first = postings[0]
        self.assertEqual("1001", first.external_id)
        self.assertEqual("Software Engineer, New Grad", first.title)
        self.assertEqual("San Francisco, CA", first.location)
        self.assertEqual("Engineering", first.department)
        self.assertIsNone(first.country)
        self.assertEqual(datetime(2026, 9, 3, 17, 30, 34, tzinfo=UTC), first.published_at)
        self.assertIn("Build payment APIs used by millions.", first.description_text)
        self.assertIn("- Experience with PostgreSQL", first.description_text)
        self.assertNotIn("<", first.description_text)

    def test_missing_optional_fields_become_none(self) -> None:
        second = GreenhouseAdapter(fixture_client("greenhouse")).fetch("examplepay")[1]

        self.assertIsNone(second.location)
        self.assertIsNone(second.department)
        self.assertIsNone(second.published_at)
        self.assertEqual("", second.description_text)


class AshbyAdapterTests(unittest.TestCase):
    def test_fetch_requests_compensation_and_skips_unlisted_jobs(self) -> None:
        requests: list[httpx2.Request] = []
        postings = AshbyAdapter(fixture_client("ashby", requests)).fetch("example")

        self.assertEqual("/posting-api/job-board/example", requests[0].url.path)
        self.assertEqual("true", requests[0].url.params["includeCompensation"])
        self.assertEqual(["a1", "a2"], [posting.external_id for posting in postings])

    def test_parses_location_salary_and_types(self) -> None:
        first, second = AshbyAdapter(fixture_client("ashby")).fetch("example")

        self.assertEqual("US", first.country)
        self.assertEqual("hybrid", first.workplace_type)
        self.assertEqual("full_time", first.employment_type)
        self.assertEqual("Research", first.department)
        self.assertEqual((150000, 190000, "USD", "year"), (
            first.salary_min, first.salary_max, first.salary_currency, first.salary_interval
        ))
        self.assertEqual("Train and ship models.\n\nRequirements: PyTorch", first.description_text)

        self.assertIsNone(second.country)
        self.assertEqual("remote", second.workplace_type)
        self.assertEqual("intern", second.employment_type)
        self.assertEqual("Platform", second.department)
        self.assertEqual((45, 55, "hour"), (second.salary_min, second.salary_max, second.salary_interval))
        self.assertEqual("- Write code", second.description_text)


class LeverAdapterTests(unittest.TestCase):
    def test_fetch_requests_json_mode(self) -> None:
        requests: list[httpx2.Request] = []
        postings = LeverAdapter(fixture_client("lever", requests)).fetch("example")

        self.assertEqual("/v0/postings/example", requests[0].url.path)
        self.assertEqual("json", requests[0].url.params["mode"])
        self.assertEqual(2, len(postings))

    def test_parses_lists_salary_and_types(self) -> None:
        first, second = LeverAdapter(fixture_client("lever")).fetch("example")

        self.assertEqual("Forward Deployed Software Engineer", first.title)
        self.assertEqual("US", first.country)
        self.assertEqual("onsite", first.workplace_type)
        self.assertEqual("full_time", first.employment_type)
        self.assertEqual((120000, 160000, "USD", "year"), (
            first.salary_min, first.salary_max, first.salary_currency, first.salary_interval
        ))
        self.assertEqual(
            "A World-Changing Company\n\nWe build software.\n\n"
            "Core Requirements\n- Java or Python\n- Active U.S. security clearance\n\n"
            "Equal opportunity employer.",
            first.description_text,
        )
        self.assertEqual(datetime.fromtimestamp(1788000000, tz=UTC), first.published_at)

        self.assertEqual("GB", second.country)
        self.assertIsNone(second.workplace_type)
        self.assertEqual("intern", second.employment_type)
        self.assertIsNone(second.salary_min)
        self.assertIsNone(second.published_at)


class FetchErrorTests(unittest.TestCase):
    def test_missing_board_raises_not_found(self) -> None:
        for adapter in (GreenhouseAdapter, AshbyAdapter, LeverAdapter):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(BoardNotFoundError):
                adapter(status_client(404)).fetch("missing")

    def test_server_error_and_bad_json_raise_fetch_error(self) -> None:
        for client in (status_client(500), status_client(200, b"not json")):
            with self.subTest(client=client), self.assertRaises(BoardFetchError):
                GreenhouseAdapter(client).fetch("example")

    def test_unexpected_payload_shape_raises_fetch_error(self) -> None:
        for adapter, body in ((GreenhouseAdapter, b"[]"), (AshbyAdapter, b"{}"), (LeverAdapter, b"{}")):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(BoardFetchError):
                adapter(status_client(200, body)).fetch("example")


if __name__ == "__main__":
    unittest.main()
