from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_db_user, get_current_user, get_db
from app.core.security import AuthenticatedUser
from app.models import User
from app.schemas.me import (
    AccountCreate,
    MeRead,
    ProfileRead,
    ProfileUpdate,
    ResumeProfileRead,
    ResumeProfileWrite,
)
from app.services import accounts

router = APIRouter(prefix="/me", tags=["me"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MeRead)
def create_me(
    data: AccountCreate,
    auth_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeRead:
    """Finish sign-up: create the users and profiles rows for the logged-in Supabase account."""
    try:
        user, profile = accounts.create_account(db, auth_user, data)
    except accounts.AccountAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
    except accounts.EmailNotConfirmedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Confirm your email, then log in again."
        )
    return MeRead.model_validate({"user": user, "profile": profile}, from_attributes=True)


@router.get("", response_model=MeRead)
def read_me(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeRead:
    """The logged-in user's account and profile; both null if sign-up isn't finished yet."""
    user, profile = accounts.get_account(db, auth_user.id)
    return MeRead.model_validate({"user": user, "profile": profile}, from_attributes=True)


@router.patch("/profile", response_model=ProfileRead)
def update_my_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
) -> ProfileRead:
    _, profile = accounts.get_account(db, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Finish sign-up first")
    return ProfileRead.model_validate(accounts.update_profile(db, user, profile, data))


@router.get("/resume", response_model=ResumeProfileRead)
def read_my_resume(
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
) -> ResumeProfileRead:
    """The latest résumé analysis the user confirmed in onboarding. 404 if there is none yet."""
    resume = accounts.get_resume_profile(db, user.id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No résumé saved yet")
    return ResumeProfileRead.model_validate(resume)


@router.put("/resume", response_model=ResumeProfileRead)
def save_my_resume(
    data: ResumeProfileWrite,
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
) -> ResumeProfileRead:
    """Save the reviewed résumé analysis, replacing any earlier one."""
    return ResumeProfileRead.model_validate(accounts.save_resume_profile(db, user, data))
