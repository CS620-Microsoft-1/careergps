"""Creating and updating a user's own account and profile."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.models import Profile, User
from app.schemas.me import AccountCreate, ProfileUpdate


class AccountAlreadyExistsError(Exception):
    """This Supabase account (or its email) already has a users row."""


class EmailNotConfirmedError(Exception):
    """The Supabase account hasn't confirmed its email yet."""


def email_is_confirmed(db: Session, user_id: uuid.UUID) -> bool:
    """Read auth.users directly instead of trusting Supabase's Confirm email setting, so an
    unconfirmed account can't claim an email it doesn't own."""
    confirmed_at = db.execute(
        text("SELECT email_confirmed_at FROM auth.users WHERE id = :id"), {"id": user_id}
    ).scalar_one_or_none()
    return confirmed_at is not None


def create_account(db: Session, auth_user: AuthenticatedUser, data: AccountCreate) -> tuple[User, Profile]:
    """Create the users and profiles rows for a confirmed Supabase account, in one transaction."""
    if db.get(User, auth_user.id) is not None:
        raise AccountAlreadyExistsError
    if not email_is_confirmed(db, auth_user.id):
        raise EmailNotConfirmedError

    user = User(id=auth_user.id, email=auth_user.email)
    # data.accept_terms is always True here (the schema rejects anything else).
    profile = Profile(user_id=auth_user.id, terms_accepted_at=datetime.now(UTC))
    try:
        db.add(user)
        db.flush()  # users row first: profiles.user_id references it
        db.add(profile)
        db.commit()
    except IntegrityError as error:
        # Two requests raced, or the email belongs to another users row.
        db.rollback()
        raise AccountAlreadyExistsError from error

    db.refresh(user)  # load server-side defaults (created_at)
    db.refresh(profile)
    return user, profile


def get_account(db: Session, user_id: uuid.UUID) -> tuple[User | None, Profile | None]:
    return db.get(User, user_id), db.get(Profile, user_id)


def update_profile(db: Session, user: User, profile: Profile, data: ProfileUpdate) -> Profile:
    changes = data.model_dump(exclude_unset=True)
    if "full_name" in changes:
        user.full_name = changes.pop("full_name")
    if changes.pop("complete_onboarding", None) and profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)
    for field, value in changes.items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile
