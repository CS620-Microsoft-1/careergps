"""Load the local certification catalog and check it against the core skill catalog.

The catalog is a reviewed JSON file for now; it is expected to move into the database later.
"""
from functools import lru_cache
import json
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.schemas.certifications import Certification
from app.services.skill_gaps.assets import ASSET_ROOT

CATALOG_PATH = BACKEND_ROOT / "data" / "certifications.json"


def core_skill_ids(core_catalog: dict) -> dict[str, set[str]]:
    return {family: {skill["skill_id"] for module in data["modules"] for skill in module["skills"]}
            for family, data in core_catalog["families"].items()}


def validate_catalog(raw: dict, core_catalog: dict) -> dict:
    """Return {"version", "certifications"} or raise ValueError naming the first bad entry."""
    known = core_skill_ids(core_catalog)
    certifications, seen = [], set()
    for entry in raw["certifications"]:
        certification = Certification.model_validate(entry)
        if certification.id in seen:
            raise ValueError(f"Duplicate certification id: {certification.id}")
        seen.add(certification.id)
        if not certification.skills:
            raise ValueError(f"{certification.id} covers no job family")
        for family, skill_ids in certification.skills.items():
            unknown = set(skill_ids) - known[family]
            if not skill_ids or unknown:
                raise ValueError(f"{certification.id} has unknown {family} skills: {sorted(unknown)}")
        certifications.append(certification)
    return {"version": str(raw["version"]), "certifications": certifications}


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    # Without the data file the API still runs and simply lists no certifications.
    if not Path(path).exists():
        return {"version": "empty", "certifications": []}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    core = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    return validate_catalog(raw, core)


@lru_cache(maxsize=1)
def get_catalog() -> dict:
    return load_catalog()


def for_family(catalog: dict, family: str) -> list[Certification]:
    return [item for item in catalog["certifications"] if family in item.skills]
