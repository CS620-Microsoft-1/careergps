from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from app.core.config import BACKEND_ROOT
from app.schemas.market import PostingSource

DATA_DIR = BACKEND_ROOT / "data"
COMPANIES_FILE = DATA_DIR / "companies.yaml"
CANDIDATES_FILE = DATA_DIR / "company_candidates.yaml"

CompanyTier = Literal["big_tech", "fortune500", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Board(StrictModel):
    source: PostingSource
    slug: str


class Company(StrictModel):
    name: str
    tier: CompanyTier
    boards: list[Board]


class Candidate(StrictModel):
    """A company to look for on the job boards; slugs override the guessed ones."""

    name: str
    tier: CompanyTier
    slugs: list[str] = []


def _load_list(path: Path, key: str) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get(key) or []
    if not isinstance(items, list):
        raise ValueError(f"{path.name}: '{key}' must be a list.")
    return items


def load_companies(path: Path = COMPANIES_FILE) -> list[Company]:
    companies = [Company.model_validate(item) for item in _load_list(path, "companies")]
    seen: set[tuple[str, str]] = set()
    for company in companies:
        for board in company.boards:
            key = (board.source, board.slug)
            if key in seen:
                raise ValueError(f"{path.name}: board {board.source}/{board.slug} is listed twice.")
            seen.add(key)
    return companies


def load_candidates(path: Path = CANDIDATES_FILE) -> list[Candidate]:
    return [Candidate.model_validate(item) for item in _load_list(path, "candidates")]
