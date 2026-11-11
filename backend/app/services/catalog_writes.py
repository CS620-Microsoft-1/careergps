"""Write the catalog tables (certifications, school_courses, student_orgs).

scripts/seed_catalog.py and the catalog refresh job both write through these functions.

- They flush but never commit: the caller commits, so a batch of changes is all or nothing.
- The "certifications" catalog version changes at most once per transaction, and only when a field
  the recommendations use changed (VERSIONED_FIELDS). Checking a row again (a new last_verified or
  source_url) keeps cached recommendations.
- After the caller commits, this process's catalog cache is cleared. Other processes see the change
  when their cache expires (catalog_store.CACHE_SECONDS).
- Ids never change and rows are never deleted. To rename, upsert a new row and deactivate the old one.
"""
from datetime import date, datetime, timezone
from functools import lru_cache
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models.catalog import CatalogCertification, CatalogVersion, SchoolCourse, StudentOrg
from app.services import catalog_store
from app.services.certifications.catalog import core_skill_ids, validate_catalog
from app.services.skill_gaps.assets import ASSET_ROOT

Kind = Literal["certification", "school_course", "student_org"]
Result = Literal["inserted", "updated", "unchanged"]

MODELS = {"certification": CatalogCertification, "school_course": SchoolCourse, "student_org": StudentOrg}
CERTIFICATIONS = "certifications"
VERSIONED_FIELDS = frozenset({"name", "provider", "url", "cost_usd", "cost_note", "level", "skills", "active"})

_VERSION_CHANGED = "catalog_writes.version_changed"
_INVALIDATE = "catalog_writes.invalidate"


@lru_cache(maxsize=1)
def _core_catalog() -> dict:
    return json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))


class _SchoolResourceData(BaseModel):
    """A school_course or student_org entry, in the shape data/resources.yaml uses."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: Literal["school_course", "student_org"] | None = None
    title: str
    provider: str
    meta: str
    description: str
    skills: list[str] = Field(min_length=1)
    school: str = Field(min_length=1)
    url: str | None = None
    alongside: bool = False


def certification_values(data: dict, verified_at: date) -> dict:
    """Columns for one certification (certifications.json shape), or ValueError."""
    raw = {**data, "last_verified": verified_at.isoformat()}
    item = validate_catalog({"version": "-", "certifications": [raw]}, _core_catalog())["certifications"][0]
    values = item.model_dump(exclude={"last_verified"})
    values["last_verified"] = verified_at
    if values["cost_usd"] is not None:
        values["cost_usd"] = round(float(values["cost_usd"]), 2)
    return values


def school_resource_values(kind: Kind, data: dict) -> dict:
    """Columns for one school course or student org (resources.yaml shape), or ValueError."""
    entry = _SchoolResourceData.model_validate(data)
    if entry.type not in (None, kind):
        raise ValueError(f"{entry.id} is a {entry.type}, not a {kind}")
    known = set().union(*core_skill_ids(_core_catalog()).values())
    unknown = set(entry.skills) - known
    if unknown:
        raise ValueError(f"{entry.id} has unknown skills: {sorted(unknown)}")
    values = entry.model_dump(exclude={"type", "alongside"})
    if kind == "student_org":
        values["alongside"] = entry.alongside
    elif entry.alongside:
        raise ValueError(f"{entry.id}: only student orgs can run alongside the plan")
    return values


def get_row(session: Session, kind: Kind, row_id: str):
    """One row from the database, active or not; skips the catalog cache. None when missing."""
    return session.get(MODELS[kind], row_id, populate_existing=True)


def upsert_certification(session: Session, data: dict, *, verified_at: date,
                         source_url: str | None = None) -> Result:
    """Add or update one certification. source_url=None keeps the stored one (new rows get the url)."""
    values = certification_values(data, verified_at)
    return _upsert(session, "certification", values, source_url=source_url or None)


def upsert_school_course(session: Session, data: dict, *, verified_at: date | None = None,
                         source_url: str | None = None) -> Result:
    """Add or update one school course. verified_at/source_url=None keep the stored values."""
    return _upsert_school(session, "school_course", data, verified_at, source_url)


def upsert_student_org(session: Session, data: dict, *, verified_at: date | None = None,
                       source_url: str | None = None) -> Result:
    """Add or update one student org. verified_at/source_url=None keep the stored values."""
    return _upsert_school(session, "student_org", data, verified_at, source_url)


def deactivate(session: Session, kind: Kind, row_id: str) -> bool:
    """Stop listing a row. False when it was already inactive; KeyError when it doesn't exist."""
    return _set_active(session, kind, row_id, False)


def reactivate(session: Session, kind: Kind, row_id: str) -> bool:
    """List a deactivated row again. False when it was already active; KeyError when it doesn't exist."""
    return _set_active(session, kind, row_id, True)


def set_catalog_version(session: Session, name: str, version: str) -> None:
    row = session.get(CatalogVersion, name)
    if row is None:
        session.add(CatalogVersion(name=name, version=version))
    else:
        row.version = version
    session.flush()


def _upsert_school(session: Session, kind: Kind, data: dict, verified_at: date | None,
                   source_url: str | None) -> Result:
    values = school_resource_values(kind, data)
    if verified_at is not None:
        values["last_verified"] = verified_at
    return _upsert(session, kind, values, source_url=source_url or None)


def _upsert(session: Session, kind: Kind, values: dict, *, source_url: str | None) -> Result:
    model = MODELS[kind]
    row = get_row(session, kind, values["id"])
    if row is None:
        sort_order = session.scalar(select(func.coalesce(func.max(model.sort_order), -1) + 1))
        session.add(model(**values, sort_order=sort_order, source_url=source_url or values.get("url")))
        session.flush()
        _changed(session, kind, versioned=True)
        return "inserted"
    if source_url is not None:
        values["source_url"] = source_url
    changed = {key for key, value in values.items() if getattr(row, key) != value}
    if not changed:
        return "unchanged"
    for key in changed:
        setattr(row, key, values[key])
    session.flush()
    _changed(session, kind, versioned=bool(changed & VERSIONED_FIELDS))
    return "updated"


def _set_active(session: Session, kind: Kind, row_id: str, active: bool) -> bool:
    row = get_row(session, kind, row_id)
    if row is None:
        raise KeyError(row_id)
    if row.active == active:
        return False
    row.active = active
    session.flush()
    _changed(session, kind, versioned=True)
    return True


def _new_version() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _changed(session: Session, kind: Kind, *, versioned: bool) -> None:
    session.info[_INVALIDATE] = True
    if kind == "certification" and versioned and not session.info.get(_VERSION_CHANGED):
        session.info[_VERSION_CHANGED] = True
        set_catalog_version(session, CERTIFICATIONS, _new_version())


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    session.info.pop(_VERSION_CHANGED, None)
    if session.info.pop(_INVALIDATE, None):
        catalog_store.invalidate()


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_VERSION_CHANGED, None)
    session.info.pop(_INVALIDATE, None)
