"""Creating and updating a student's account (users row) and their confirmed résumés.

The rules that don't need the database (contact details, university, file type) are plain functions so
they can be tested without one. AccountService holds the database part.
"""
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.options import DEFAULT_UNIVERSITY
from app.core.security import AuthenticatedUser
from app.models import Resume, User
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


def contact_details(classification: ResumeClassification) -> dict:
    """The users columns that come from the résumé, as found in this one."""
    personal = classification.personal_information
    return {
        "full_name": (personal.name or "").strip()[:255] or None,
        "resume_emails": list(dict.fromkeys(personal.emails)),
        "phones": list(dict.fromkeys(personal.phones)),
        "current_location": personal.location,
        "linkedin_url": personal.linkedin,
        "github_url": personal.github,
        "website_url": personal.website,
    }


def fill_empty_contacts(user: User, classification: ResumeClassification) -> None:
    """A newer résumé fills only fields that are still empty; it never overwrites one."""
    for field, value in contact_details(classification).items():
        if not getattr(user, field) and value:
            setattr(user, field, value)


def university_from(classification: ResumeClassification) -> str:
    """The first school listed in the résumé's education; DEFAULT_UNIVERSITY if there is none."""
    for entry in classification.education:
        name = (entry.institution or "").strip()
        if name:
            return name[:150]
    return DEFAULT_UNIVERSITY


def new_user(auth_user: AuthenticatedUser, data: AccountCreate) -> User:
    user = User(
        id=auth_user.id,
        primary_email=auth_user.email.lower(),
        first_name=data.first_name,
        last_name=data.last_name,
        target_role=data.target_role,
        experience_level=data.experience_level,
        graduation_year=data.graduation_year,
        university=university_from(data.resume.classification),
        preferred_location=data.preferred_location,
        terms_accepted_at=datetime.now(UTC),
        **{field: value for field, value in contact_details(data.resume.classification).items()},
    )
    return user


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

    def email_is_confirmed(self, user_id: uuid.UUID) -> bool:
        """Read auth.users directly instead of trusting Supabase's Confirm email setting, so an
        unconfirmed account can't claim an email it doesn't own."""
        confirmed_at = self.db.execute(
            text("SELECT email_confirmed_at FROM auth.users WHERE id = :id"), {"id": user_id}
        ).scalar_one_or_none()
        return confirmed_at is not None

    def create_account(self, auth_user: AuthenticatedUser, data: AccountCreate) -> User:
        """Create the users row and its first résumé in one transaction; the résumé becomes active."""
        if self.get_user(auth_user.id) is not None:
            raise AccountAlreadyExistsError
        if not self.email_is_confirmed(auth_user.id):
            raise EmailNotConfirmedError
        user = new_user(auth_user, data)
        resume = new_resume(user.id, data.resume)
        try:
            self.db.add(user)
            self.db.flush()  # users first: resumes.user_id references it
            self.db.add(resume)
            self.db.flush()
            user.active_resume_id = resume.id
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

    def add_resume(self, user: User, data: ResumeSubmit) -> Resume:
        """Save a newer confirmed résumé, make it the active one, and fill empty contact fields."""
        resume = new_resume(user.id, data)
        self.db.add(resume)
        self.db.flush()
        user.active_resume_id = resume.id
        fill_empty_contacts(user, data.classification)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def get_active_resume(self, user: User) -> Resume | None:
        return self.db.get(Resume, user.active_resume_id) if user.active_resume_id else None

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
