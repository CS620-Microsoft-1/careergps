"""Uploading, retrying and confirming a user's résumé (SPEC-001 §5.3–5.4, §6)."""
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Education,
    Experience,
    Profile,
    Project,
    Resume,
    ResumeStatus,
    Skill,
    User,
)
from app.schemas.resume import ResumeConfirm
from app.services import pdf
from app.services.parsing import fail_if_stuck
from app.services.storage import FileStorage, StorageError

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/pdf"


class ResumeNotFoundError(Exception):
    pass


class ResumeConflictError(Exception):
    """The résumé is in the wrong state for this action. The message is safe to show the user."""


def _display_name(filename: str | None) -> str:
    # Shown in the UI only; drop any path the browser sent.
    name = PureWindowsPath(PurePosixPath(filename or "").name).name.strip()
    return (name or "resume.pdf")[:255]


def get_for_user(db: Session, user_id: uuid.UUID) -> Resume | None:
    resume = db.scalar(select(Resume).where(Resume.user_id == user_id))
    if resume is not None:
        fail_if_stuck(db, resume)
    return resume


def get_owned(db: Session, user: User, resume_id: uuid.UUID) -> Resume:
    """Another user's résumé is reported as not found, never as forbidden."""
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    if resume is None:
        raise ResumeNotFoundError
    fail_if_stuck(db, resume)
    return resume


def upload(db: Session, storage: FileStorage, user: User, filename: str | None, data: bytes) -> Resume:
    """Store a new PDF. P0: one résumé per user; only a failed one may be replaced."""
    pdf.page_count(data)  # raises InvalidPdfError

    existing = get_for_user(db, user.id)
    if existing is not None:
        if existing.status != ResumeStatus.FAILED:
            raise ResumeConflictError("You already have a résumé.")
        _delete_file(storage, existing.storage_key)
        db.delete(existing)
        db.flush()

    resume_id = uuid.uuid4()
    resume = Resume(
        id=resume_id,
        user_id=user.id,
        storage_key=f"{user.id}/{resume_id}.pdf",
        original_filename=_display_name(filename),
        content_type=CONTENT_TYPE,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        status=ResumeStatus.PENDING,
    )
    storage.put(resume.storage_key, data, CONTENT_TYPE)  # raises StorageError
    db.add(resume)
    try:
        db.commit()
    except IntegrityError as error:  # a parallel upload won the race
        db.rollback()
        _delete_file(storage, resume.storage_key)
        raise ResumeConflictError("You already have a résumé.") from error
    db.refresh(resume)
    return resume


def retry(db: Session, resume: Resume) -> Resume:
    if resume.status != ResumeStatus.FAILED:
        raise ResumeConflictError("Only a résumé that failed to parse can be retried.")
    resume.status = ResumeStatus.PENDING
    resume.error_code = None
    db.commit()
    db.refresh(resume)
    return resume


def confirm(db: Session, user: User, resume: Resume, data: ResumeConfirm) -> Resume:
    """Write the user-confirmed data to the structured tables, all in one transaction."""
    if resume.status != ResumeStatus.PARSED:
        raise ResumeConflictError("Only a parsed résumé can be confirmed.")

    for model in (Education, Experience, Skill, Project):
        db.execute(delete(model).where(model.user_id == user.id))

    owner = {"user_id": user.id, "resume_id": resume.id}
    db.add_all(Education(**owner, **item.model_dump()) for item in data.education)
    db.add_all(
        Experience(
            **owner,
            **item.model_dump(exclude={"bullets"}),
            description="\n".join(item.bullets) or None,
        )
        for item in data.experience
    )
    db.add_all(Project(**owner, **item.model_dump()) for item in data.projects)
    seen: set[str] = set()
    for skill in data.skills:
        if skill.name.lower() not in seen:
            seen.add(skill.name.lower())
            db.add(Skill(**owner, **skill.model_dump()))

    now = datetime.now(UTC)
    profile = db.get(Profile, user.id)
    if profile is not None:
        profile.phone = data.contact.phone
        profile.links = data.contact.links or None
        profile.onboarding_completed_at = profile.onboarding_completed_at or now

    resume.parsed_data = data.model_dump()
    resume.status = ResumeStatus.CONFIRMED
    resume.confirmed_at = now
    db.commit()
    db.refresh(resume)
    return resume


def _delete_file(storage: FileStorage, key: str) -> None:
    try:
        storage.delete(key)
    except StorageError:
        # Leaves an orphaned file, but must not block the user. Logged for cleanup.
        logger.exception("Could not delete stored résumé %s", key)
