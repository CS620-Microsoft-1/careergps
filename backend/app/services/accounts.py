"""Creating and updating a user's own account and profile."""
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.models import Profile, User
from app.schemas.me import AccountCreate, ProfileUpdate


class AccountAlreadyExistsError(Exception):
    """This Supabase account (or its email) already has a users row."""


def create_account(db: Session, auth_user: AuthenticatedUser, data: AccountCreate) -> tuple[User, Profile]:
    """Create the users and profiles rows for a confirmed Supabase account, in one transaction."""
    if db.get(User, auth_user.id) is not None:
        raise AccountAlreadyExistsError

    user = User(id=auth_user.id, email=auth_user.email, full_name=data.full_name)
    profile = Profile(
        user_id=auth_user.id,
        target_role=data.target_role,
        experience_level=data.experience_level,
        graduation_year=data.graduation_year,
        university=data.university,
        terms_accepted_at=datetime.now(UTC),
    )
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


def update_profile(db: Session, profile: Profile, data: ProfileUpdate) -> Profile:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile
