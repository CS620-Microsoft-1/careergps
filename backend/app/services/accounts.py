"""Creating and updating a student's account (users row) and their confirmed résumés.

The rules that don't need the database (contact details, file type) are plain functions so
they can be tested without one. AccountService holds the database part.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.options import JOB_FAMILY_BY_ROLE, JobFamily
from app.core.security import AuthenticatedUser
from app.models import Destination, Resume, User
from app.schemas.me import AccountCreate, AccountUpdate, ResumeSubmit
from app.schemas.resume import ResumeClassification

logger = logging.getLogger(__name__)

# Version of the ResumeClassification contract stored in resumes.schema_version.
RESUME_SCHEMA_VERSION = "1"

# users columns filled from the résumé's personal information.
CONTACT_FIELDS = ("full_name", "resume_emails", "phones", "current_location", "linkedin_url", "github_url", "website_url")


class AccountAlreadyExistsError(Exception):
    """This Supabase account (or its email) already has a users row."""


class EmailNotConfirmedError(Exception):
    """The Supabase account hasn't confirmed its email yet."""


@dataclass(frozen=True)
class SignupRecord:
    """What Supabase recorded about the sign-up (auth.users)."""

    created_at: datetime
    email_confirmed_at: datetime | None


def _column_length(column: str) -> int:
    return User.__table__.c[column].type.length


def _fit_text(value: str | None, column: str) -> str | None:
    """Trimmed and cut to the column's length; the résumé contract has no length limits."""
    value = (value or "").strip()
    return value[: _column_length(column)] or None


def _fit_url(value: str | None, column: str) -> str | None:
    """A URL longer than its column is dropped rather than cut, since a cut URL doesn't work."""
    value = (value or "").strip()
    return value if value and len(value) <= _column_length(column) else None


def contact_details(classification: ResumeClassification) -> dict:
    """The users columns that come from the résumé, as found in this one."""
    personal = classification.personal_information
    return {
        "full_name": _fit_text(personal.name, "full_name"),
        # Emails are case-insensitive: A@x.com and a@x.com are the same address.
        "resume_emails": list(dict.fromkeys(e.strip().lower() for e in personal.emails if e.strip())),
        "phones": list(dict.fromkeys(p.strip() for p in personal.phones if p.strip())),
        "current_location": _fit_text(personal.location, "current_location"),
        "linkedin_url": _fit_url(personal.linkedin, "linkedin_url"),
        "github_url": _fit_url(personal.github, "github_url"),
        "website_url": _fit_url(personal.website, "website_url"),
    }


def fill_empty_contacts(user: User, classification: ResumeClassification) -> None:
    """A newer résumé fills only fields that are still empty; it never overwrites one."""
    for field, value in contact_details(classification).items():
        if not getattr(user, field) and value:
            setattr(user, field, value)


def new_user(auth_user: AuthenticatedUser, data: AccountCreate, signed_up_at: datetime) -> User:
    user = User(
        id=auth_user.id,
        primary_email=auth_user.email.lower(),
        first_name=data.first_name,
        last_name=data.last_name,
        target_role=data.target_role,
        experience_level=data.experience_level,
        graduation_year=data.graduation_year,
        university=data.university,
        preferred_location=data.preferred_location,
        # Sign-up can't be submitted without ticking the terms box, so its time is the consent time.
        terms_accepted_at=signed_up_at,
        **{field: value for field, value in contact_details(data.resume.classification).items()},
    )
    return user


def role_family(target_role: str) -> JobFamily | None:
    """The destination (job family) a target role stands for, or None for an unsupported role."""
    return JOB_FAMILY_BY_ROLE.get(target_role)


def new_resume(user_id: uuid.UUID, data: ResumeSubmit) -> Resume:
    return Resume(
        id=uuid.uuid4(),
        user_id=user_id,
        original_filename=data.original_filename,
        file_type=data.original_filename.rsplit(".", 1)[-1].lower(),
        parser=data.parser,
        ocr_pages=data.ocr_pages,
        agent_name=data.agent_name,
        schema_version=RESUME_SCHEMA_VERSION,
        confirmed_data=data.classification.model_dump(mode="json"),
    )


class AccountService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def signup_record(self, user_id: uuid.UUID) -> SignupRecord | None:
        """Read auth.users directly (the database role needs SELECT on it; see backend/README.md).
        Supabase writes created_at, so the browser can't change it."""
        row = self.db.execute(
            text("SELECT created_at, email_confirmed_at FROM auth.users WHERE id = :id"), {"id": user_id}
        ).one_or_none()
        return SignupRecord(row.created_at, row.email_confirmed_at) if row else None

    def create_account(self, auth_user: AuthenticatedUser, data: AccountCreate) -> User:
        """Create the users row, its first résumé and the destination for the chosen role in one transaction."""
        if self.get_user(auth_user.id) is not None:
            raise AccountAlreadyExistsError
        signup = self.signup_record(auth_user.id)
        if signup is None or signup.email_confirmed_at is None:
            raise EmailNotConfirmedError
        user = new_user(auth_user, data, signed_up_at=signup.created_at)
        resume = new_resume(user.id, data.resume)
        family = role_family(data.target_role)
        try:
            self.db.add(user)
            self.db.flush()  # users first: resumes.user_id references it
            self.db.add(resume)
            self.db.flush()  # then the résumé the destination points at
            if family is not None:
                self.db.add(Destination(user_id=user.id, job_family=family, resume_id=resume.id))
            self.db.commit()
        except IntegrityError as error:
            # Two requests raced, or the email belongs to another users row.
            self.db.rollback()
            raise AccountAlreadyExistsError from error
        self.db.refresh(user)
        return user

    def update_account(self, user: User, data: AccountUpdate) -> User:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        self.db.commit()
        self.db.refresh(user)
        return user

    def add_resume(self, user: User, data: ResumeSubmit, job_family: JobFamily) -> Resume:
        """Save a confirmed résumé, use it for this destination, and fill empty contact fields."""
        fill_empty_contacts(user, data.classification)
        resume = new_resume(user.id, data)
        self._insert_resume(resume)
        self._point(user, job_family, resume.id)
        return resume

    def use_resume(self, user: User, job_family: JobFamily, resume_id: uuid.UUID) -> Resume | None:
        """Match a destination (new or existing) against one of the student's résumés. None if it isn't theirs."""
        resume = self.get_owned_resume(user, resume_id)
        if resume is not None:
            self._point(user, job_family, resume.id)
        return resume

    def get_resume(self, user: User, job_family: JobFamily | None) -> Resume | None:
        """The résumé a destination uses, or None if the student hasn't added that role."""
        if job_family is None:
            return None
        destination = self.db.get(Destination, (user.id, job_family))
        return self.db.get(Resume, destination.resume_id) if destination else None

    def get_owned_resume(self, user: User, resume_id: uuid.UUID) -> Resume | None:
        resume = self.db.get(Resume, resume_id)
        return resume if resume is not None and resume.user_id == user.id else None

    def list_resumes(self, user: User) -> list[Resume]:
        """Every confirmed version, newest first."""
        query = select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc())
        return list(self.db.scalars(query))

    def list_destinations(self, user: User) -> list[Destination]:
        """The roles the student has added, oldest first."""
        query = select(Destination).where(Destination.user_id == user.id).order_by(Destination.created_at)
        return list(self.db.scalars(query))

    def end_reads(self) -> None:
        """End the request's read transaction before slow work (Agent calls) so it doesn't hold a
        transaction-pooler connection. Commit, not rollback: loaded objects stay usable
        (expire_on_commit=False), and a later query starts a new transaction."""
        self.db.commit()

    def _insert_resume(self, resume: Resume) -> None:
        self.db.add(resume)
        self.db.flush()

    def _point(self, user: User, job_family: JobFamily, resume_id: uuid.UUID) -> None:
        """Add the destination or switch its résumé in one upsert. A get-then-insert let two requests
        adding the same new role (double click, or POST /me/resumes + PUT /me/destinations) both insert."""
        statement = insert(Destination).values(user_id=user.id, job_family=job_family, resume_id=resume_id)
        statement = statement.on_conflict_do_update(
            index_elements=[Destination.user_id, Destination.job_family],
            set_={"resume_id": statement.excluded.resume_id, "updated_at": func.now()},
        )
        # RETURNING + populate_existing refreshes a Destination this session already loaded.
        self.db.scalars(statement.returning(Destination).execution_options(populate_existing=True)).one()
        self.db.commit()

    def sync_email(self, user: User, email: str) -> None:
        """Keep primary_email equal to the Supabase login email (it can change in Supabase)."""
        email = email.lower()
        if user.primary_email == email:
            return
        user.primary_email = email
        try:
            self.db.commit()
        except IntegrityError:
            # Another users row has this email; keep the old one rather than fail the request.
            self.db.rollback()
            logger.warning("Could not sync primary_email for user %s: email already in use", user.id)
