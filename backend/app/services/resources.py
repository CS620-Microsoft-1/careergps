"""The curated resource catalog (data/resources.yaml), filtered by role and school."""
from functools import lru_cache
import re

import yaml

from app.core.config import BACKEND_ROOT
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.storage import load

CATALOG_PATH = BACKEND_ROOT / "data" / "resources.yaml"

# Spellings students use for the same school, after _school_key.
_SCHOOL_ALIASES = {"uwmadison": "universityofwisconsinmadison"}


def _school_key(name: str | None) -> str:
    key = re.sub(r"[^a-z]", "", (name or "").lower())
    return _SCHOOL_ALIASES.get(key, key)


@lru_cache
def load_catalog() -> tuple[dict, ...]:
    entries = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))["resources"]
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate resource id in data/resources.yaml")
    return tuple(entries)


@lru_cache
def family_skills(family: str) -> frozenset[str]:
    catalog = load(ASSET_ROOT / "core_catalog.json")
    return frozenset(skill["skill_id"] for module in catalog["families"][family]["modules"]
                     for skill in module["skills"])


def resources_for(family: str, university: str | None) -> list[dict]:
    """Resources that close at least one of the role's skills; school ones only for that school."""
    skills = family_skills(family)
    school = _school_key(university)
    result = []
    for entry in load_catalog():
        if entry.get("school") and _school_key(entry["school"]) != school:
            continue
        closes = [skill for skill in entry["skills"] if skill in skills]
        if closes:
            result.append({**entry, "skills": closes})
    return result
