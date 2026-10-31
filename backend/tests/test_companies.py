import io
import os
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from pydantic import ValidationError

from app.services.postings.companies import Candidate, load_candidates, load_companies
from scripts.probe_boards import probe, slug_guesses


def write_yaml(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    return Path(handle.name)


class CompanyFileTests(unittest.TestCase):
    def test_committed_company_files_are_valid(self) -> None:
        companies = load_companies()
        self.assertGreater(len(companies), 0)
        self.assertTrue(all(company.boards for company in companies))
        self.assertGreater(len(load_candidates()), 0)

    def test_duplicate_board_is_rejected(self) -> None:
        path = write_yaml(
            "companies:\n"
            "  - {name: A, tier: other, boards: [{source: greenhouse, slug: a}]}\n"
            "  - {name: B, tier: other, boards: [{source: greenhouse, slug: a}]}\n"
        )
        with self.assertRaisesRegex(ValueError, "listed twice"):
            load_companies(path)

    def test_unknown_source_or_tier_is_rejected(self) -> None:
        for entry in (
            "{name: A, tier: other, boards: [{source: workday, slug: a}]}",
            "{name: A, tier: startup, boards: [{source: lever, slug: a}]}",
        ):
            with self.subTest(entry=entry), self.assertRaises(ValidationError):
                load_companies(write_yaml(f"companies:\n  - {entry}\n"))


class SlugGuessTests(unittest.TestCase):
    def test_guesses_joined_and_hyphenated_names(self) -> None:
        self.assertEqual(["scaleai", "scale-ai"], slug_guesses(Candidate(name="Scale AI", tier="other")))
        self.assertEqual(["stripe"], slug_guesses(Candidate(name="Stripe", tier="other")))

    def test_explicit_slugs_replace_guesses(self) -> None:
        candidate = Candidate(name="Lucid Motors", tier="other", slugs=["lucid"])
        self.assertEqual(["lucid"], slug_guesses(candidate))



def fake_adapter(source: str, boards: dict):
    class FakeAdapter:
        def __init__(self, _client) -> None:
            self.source = source

        def fetch(self, slug: str):
            result = boards.get(slug)
            if isinstance(result, Exception):
                raise result
            return result or []

    return FakeAdapter


class ProbeTests(unittest.TestCase):
    def test_malformed_posting_skips_only_that_board(self) -> None:
        posting = SimpleNamespace(title="Software Engineer", country="US")
        candidates = [
            Candidate(name="Broken", tier="other", slugs=["broken"]),
            Candidate(name="Good", tier="other", slugs=["good"]),
        ]
        stderr = io.StringIO()
        with (
            patch("scripts.probe_boards.create_http_client", lambda: nullcontext()),
            patch("scripts.probe_boards.time.sleep"),
            patch("scripts.probe_boards.GreenhouseAdapter",
                  fake_adapter("greenhouse", {"broken": KeyError("title"), "good": [posting]})),
            patch("scripts.probe_boards.AshbyAdapter", fake_adapter("ashby", {})),
            patch("scripts.probe_boards.LeverAdapter", fake_adapter("lever", {})),
            redirect_stderr(stderr),
        ):
            found = probe(candidates)

        self.assertEqual(
            [{"name": "Good", "tier": "other", "boards": [{"source": "greenhouse", "slug": "good"}]}],
            found,
        )
        self.assertIn("! Broken greenhouse/broken: Unexpected KeyError", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
