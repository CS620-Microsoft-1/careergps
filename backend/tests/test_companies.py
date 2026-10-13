import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from pydantic import ValidationError

from app.services.postings.companies import Candidate, load_candidates, load_companies
from scripts.probe_boards import slug_guesses


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


if __name__ == "__main__":
    unittest.main()
