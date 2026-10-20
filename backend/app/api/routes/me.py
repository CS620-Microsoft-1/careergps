from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_account_service, get_current_db_user, get_current_user
from app.core.security import AuthenticatedUser
from app.models import Resume, User
from app.schemas.me import AccountCreate, AccountUpdate, MeRead, ResumeRead, ResumeSubmit, UserRead
from app.services.accounts import (
    AccountAlreadyExistsError,
    AccountService,
    EmailNotConfirmedError,
)

router = APIRouter(prefix="/me", tags=["me"])


def _resume_read(resume: Resume) -> ResumeRead:
    return ResumeRead.model_validate(
        {
            "id": resume.id,
            "original_filename": resume.original_filename,
            "file_type": resume.file_type,
            "classification": resume.confirmed_data,
            "created_at": resume.created_at,
        }
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MeRead)
def create_me(
    data: AccountCreate,
    auth_user: AuthenticatedUser = Depends(get_current_user),
    accounts: AccountService = Depends(get_account_service),
) -> MeRead:
    """Finish onboarding: create the users row and the first confirmed résumé."""
    try:
        user = accounts.create_account(auth_user, data)
    except AccountAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
    except EmailNotConfirmedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Confirm your email, then log in again."
        )
    return MeRead(user=UserRead.model_validate(user))


@router.get("", response_model=MeRead)
def read_me(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    accounts: AccountService = Depends(get_account_service),
) -> MeRead:
    """The logged-in student's account; null until onboarding is finished."""
    user = accounts.get_user(auth_user.id)
    if user is None:
        return MeRead(user=None)
    accounts.sync_email(user, auth_user.email)
    return MeRead(user=UserRead.model_validate(user))


@router.patch("", response_model=UserRead)
def update_me(
    data: AccountUpdate,
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> UserRead:
    return UserRead.model_validate(accounts.update_account(user, data))


@router.get("/resume", response_model=ResumeRead)
def read_my_resume(
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> ResumeRead:
    """The active résumé (the newest confirmed one). 404 if there is none."""
    resume = accounts.get_active_resume(user)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No résumé saved yet")
    return _resume_read(resume)


@router.post("/resumes", status_code=status.HTTP_201_CREATED, response_model=ResumeRead)
def add_my_resume(
    data: ResumeSubmit,
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> ResumeRead:
    """Save a newer confirmed résumé; it becomes the active one. Earlier versions are kept."""
    return _resume_read(accounts.add_resume(user, data))
