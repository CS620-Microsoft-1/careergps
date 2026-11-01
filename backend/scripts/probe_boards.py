"""Find which candidate companies have a public Greenhouse, Ashby or Lever job board.

Run from backend/:
    python -m scripts.probe_boards                 # print matches as YAML
    python -m scripts.probe_boards --write         # also write data/companies.yaml

Review the output before committing it: a slug can belong to a different company with
the same name. The Greenhouse company name and a sample job title are printed to help.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.postings.ashby import AshbyAdapter
from app.services.postings.base import BoardFetchError, BoardNotFoundError, create_http_client
from app.services.postings.companies import COMPANIES_FILE, Candidate, load_candidates
from app.services.postings.greenhouse import GreenhouseAdapter
from app.services.postings.lever import LeverAdapter

REQUEST_DELAY_SECONDS = 0.5
HEADER = (
    "# Job boards ingested daily by scripts/ingest_postings.py.\n"
    "# Generated with scripts/probe_boards.py from data/company_candidates.yaml, then reviewed by hand.\n"
)


def slug_guesses(candidate: Candidate) -> list[str]:
    if candidate.slugs:
        return candidate.slugs
    words = re.findall(r"[a-z0-9]+", candidate.name.lower())
    return list(dict.fromkeys(["".join(words), "-".join(words)]))


def probe(candidates: list[Candidate]) -> list[dict]:
    found = []
    with create_http_client() as client:
        adapters = [GreenhouseAdapter(client), AshbyAdapter(client), LeverAdapter(client)]
        for candidate in candidates:
            boards = []
            for adapter in adapters:
                for slug in slug_guesses(candidate):
                    time.sleep(REQUEST_DELAY_SECONDS)
                    try:
                        postings = adapter.fetch(slug)
                    except BoardNotFoundError:
                        continue
                    except BoardFetchError as error:
                        print(f"  ! {candidate.name} {adapter.source}/{slug}: {error}", file=sys.stderr)
                        continue
                    except Exception as error:
                        # One malformed posting must not abort the probe and lose --write.
                        print(
                            f"  ! {candidate.name} {adapter.source}/{slug}: "
                            f"Unexpected {type(error).__name__}: {error}",
                            file=sys.stderr,
                        )
                        continue
                    if not postings:
                        continue
                    us = sum(posting.country == "US" for posting in postings)
                    print(
                        f"  + {candidate.name}: {adapter.source}/{slug} "
                        f"({len(postings)} postings, {us} tagged US) e.g. {postings[0].title!r}",
                        file=sys.stderr,
                    )
                    boards.append({"source": adapter.source, "slug": slug})
                    break
            if boards:
                found.append({"name": candidate.name, "tier": candidate.tier, "boards": boards})
            else:
                print(f"  - {candidate.name}: no board found", file=sys.stderr)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help=f"write the result to {COMPANIES_FILE.name}")
    args = parser.parse_args()

    found = probe(load_candidates())
    output = HEADER + yaml.safe_dump({"companies": found}, sort_keys=False, allow_unicode=True)
    print(output)
    if args.write:
        COMPANIES_FILE.write_text(output, encoding="utf-8")
        print(f"Wrote {len(found)} companies to {COMPANIES_FILE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
