"""Read certifications, school courses and student organizations for the API, with a short cache.

The database tables (app/models/catalog.py) are the source. get_snapshot() keeps what it read for
CACHE_SECONDS, so a change written by another process shows up within that time.

- Tables missing (migration not applied yet) or all three empty (not seeded yet): read the files
  data/certifications.json and data/resources.yaml instead, and log a warning.
- Any other database error: keep serving the last snapshot and try again after RETRY_SECONDS; with
  no snapshot yet, the request fails with 503.

Only active rows are listed. To read one row whatever its state, use catalog_writes.get_row.
Unit tests read the files (tests/__init__.py): CI has no database.
"""
from dataclasses import dataclass
import logging
from threading import Lock
import time
from typing import Callable

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.catalog import CatalogCertification, CatalogVersion, SchoolCourse, StudentOrg
from app.schemas.certifications import Certification

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300
RETRY_SECONDS = 30
# resources.yaml entry types that now live in the database; online courses are still read from the file.
DATABASE_TYPES = ("school_course", "student_org")
# school_courses columns from the course guide; in an entry only when set.
COURSE_FIELDS = ("course_code", "credits", "last_taught")


@dataclass(frozen=True)
class CatalogSnapshot:
    source: str  # "database" or "files"
    certification_version: str
    certifications: tuple[Certification, ...]
    # Dicts in the data/resources.yaml entry shape.
    school_courses: tuple[dict, ...]
    student_orgs: tuple[dict, ...]


class CatalogNotReady(Exception):
    """The catalog tables don't exist or are all empty."""


class CatalogUnavailable(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The resource catalog is unavailable")


class FileCatalogSource:
    """The catalog as it was before the database: the reviewed data files."""

    def load(self) -> CatalogSnapshot:
        from app.services.certifications.catalog import load_catalog as load_certifications
        from app.services.resources import load_catalog as load_resources

        certifications = load_certifications()
        entries = load_resources()
        return CatalogSnapshot(
            source="files",
            certification_version=certifications["version"],
            certifications=tuple(certifications["certifications"]),
            school_courses=tuple(entry for entry in entries if entry["type"] == "school_course"),
            student_orgs=tuple(entry for entry in entries if entry["type"] == "student_org"),
        )


class DatabaseCatalogSource:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory = session_factory

    def load(self) -> CatalogSnapshot:
        if self._session_factory is None:
            from app.db.session import SessionLocal

            self._session_factory = SessionLocal
        try:
            with self._session_factory() as session:
                certifications = _active(session, CatalogCertification)
                courses = _active(session, SchoolCourse)
                orgs = _active(session, StudentOrg)
                if not (certifications or courses or orgs) and not any(
                    session.scalar(select(exists().select_from(model)))
                    for model in (CatalogCertification, SchoolCourse, StudentOrg)
                ):
                    raise CatalogNotReady("empty")
                version = session.scalar(select(CatalogVersion.version).where(CatalogVersion.name == "certifications"))
        except ProgrammingError as error:
            if getattr(error.orig, "sqlstate", None) == "42P01":  # undefined_table
                raise CatalogNotReady("missing") from None
            raise
        return CatalogSnapshot(
            source="database",
            certification_version=version or "database",
            certifications=tuple(_certification(row) for row in certifications),
            school_courses=tuple(_school_resource(row, "school_course") for row in courses),
            student_orgs=tuple(_school_resource(row, "student_org") for row in orgs),
        )


def _active(session: Session, model) -> list:
    return list(session.scalars(select(model).where(model.active).order_by(model.sort_order, model.id)))


def _certification(row: CatalogCertification) -> Certification:
    return Certification(id=row.id, name=row.name, provider=row.provider, url=row.url, cost_usd=row.cost_usd,
                         cost_note=row.cost_note, level=row.level, skills=row.skills,
                         last_verified=row.last_verified.isoformat())


def _school_resource(row, kind: str) -> dict:
    entry = {"id": row.id, "type": kind, "title": row.title, "provider": row.provider, "meta": row.meta,
             "description": row.description, "skills": list(row.skills), "school": row.school}
    if kind == "student_org":
        entry["alongside"] = row.alongside
    else:
        entry.update({field: getattr(row, field) for field in COURSE_FIELDS if getattr(row, field) is not None})
    if row.url is not None:
        entry["url"] = row.url
    return entry


_lock = Lock()
_source = DatabaseCatalogSource()
_snapshot: CatalogSnapshot | None = None
_expires_at = 0.0


def get_snapshot() -> CatalogSnapshot:
    global _snapshot, _expires_at
    with _lock:
        now = time.monotonic()
        if _snapshot is not None and now < _expires_at:
            return _snapshot
        try:
            snapshot = _source.load()
        except CatalogNotReady as reason:
            logger.warning("Catalog tables are %s; reading the catalog files", reason)
            snapshot = FileCatalogSource().load()
        except SQLAlchemyError as error:
            if _snapshot is None:
                logger.error("Catalog query failed (%s) and nothing is cached", type(error).__name__)
                raise CatalogUnavailable() from None
            logger.error("Catalog query failed (%s); keeping the cached catalog", type(error).__name__)
            _expires_at = now + RETRY_SECONDS
            return _snapshot
        _snapshot, _expires_at = snapshot, now + CACHE_SECONDS
        return snapshot


def invalidate() -> None:
    """Read again on the next request. The current snapshot stays as the fallback for database errors."""
    global _expires_at
    with _lock:
        _expires_at = 0.0


def use_source(source) -> None:
    """Read from another source (tests); drops the cached snapshot."""
    global _source, _snapshot, _expires_at
    with _lock:
        _source, _snapshot, _expires_at = source, None, 0.0
