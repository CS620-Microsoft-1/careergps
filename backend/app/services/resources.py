"""The curated resource catalog (data/resources.yaml plus certifications and projects), filtered by role and school."""
from functools import lru_cache
import json
import re

import yaml

from app.core.config import BACKEND_ROOT
from app.services.certifications.catalog import get_catalog as certification_catalog
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.storage import load

CATALOG_PATH = BACKEND_ROOT / "data" / "resources.yaml"
PROJECTS_PATH = BACKEND_ROOT / "data" / "projects.json"

# projects.json names roles by career path.
FAMILY_TO_CATALOG = {
    "software_engineer": "Software Engineering",
    "data_analyst": "Data Analyst",
    "ai_engineer": "AI/ML Engineering",
}

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
def load_projects() -> tuple[dict, ...]:
    return tuple(json.loads(PROJECTS_PATH.read_text(encoding="utf-8")))


def _project(project: dict) -> dict:
    """A projects.json entry (the resources agent's catalog) as a resource."""
    return {"id": project["id"], "type": "project", "title": project["title"], "provider": "Project",
            "meta": f"{project['difficulty'].capitalize()} · about {project['estimated_hours']} hours",
            "description": project["description"], "skills": project["supported_skill_ids"]}


def _certification(item, family: str) -> dict:
    """A certifications.json entry as a resource; its skills are listed per role."""
    cost = "Free" if item.cost_usd == 0 else f"${item.cost_usd:g} · {item.cost_note}"
    return {"id": item.id, "type": "certification", "title": item.name, "provider": item.provider,
            "meta": f"{item.level.capitalize()} · {cost}", "description": "", "skills": item.skills[family],
            "url": item.url}


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
    certifications = [_certification(item, family) for item in certification_catalog()["certifications"]
                      if family in item.skills]
    projects = [_project(project) for project in load_projects() if project["career_path"] == FAMILY_TO_CATALOG[family]]
    for entry in [*load_catalog(), *certifications, *projects]:
        if entry.get("school") and _school_key(entry["school"]) != school:
            continue
        closes = [skill for skill in entry["skills"] if skill in skills]
        if closes:
            result.append({**entry, "skills": closes})
    return result
