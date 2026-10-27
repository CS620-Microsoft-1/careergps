import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_account_service, get_current_db_user, get_current_user
from app.core.options import JobFamily
from app.core.security import AuthenticatedUser
from app.models import Resume, User
from app.schemas.me import (
    AccountCreate,
    AccountUpdate,
    DestinationRead,
    DestinationUpdate,
    MeRead,
    ResumeAdd,
    ResumeRead,
    ResumeSummary,
    UserRead,
)
from app.services.accounts import (
    AccountAlreadyExistsError,
    AccountService,
    EmailNotConfirmedError,
    role_family,
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
    job_family: JobFamily | None = None,
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> ResumeRead:
    """A destination's résumé: job_family, or the selected target role's by default. 404 if it has none."""
    resume = accounts.get_resume(user, job_family or role_family(user.target_role))
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No résumé saved for this role yet")
    return _resume_read(resume)


@router.post("/resumes", status_code=status.HTTP_201_CREATED, response_model=ResumeRead)
def add_my_resume(
    data: ResumeAdd,
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> ResumeRead:
    """Save a confirmed résumé for one destination. Earlier versions are kept."""
    return _resume_read(accounts.add_resume(user, data, data.job_family))


@router.get("/resumes", response_model=list[ResumeSummary])
def list_my_resumes(
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> list[ResumeSummary]:
    """Every confirmed résumé version, newest first, with the roles that use each one."""
    used_by: dict[uuid.UUID, list[str]] = {}
    for destination in accounts.list_destinations(user):
        used_by.setdefault(destination.resume_id, []).append(destination.job_family)
    return [
        ResumeSummary(
            id=resume.id,
            label=resume.label,
            original_filename=resume.original_filename,
            file_type=resume.file_type,
            created_at=resume.created_at,
            destinations=used_by.get(resume.id, []),
        )
        for resume in accounts.list_resumes(user)
    ]


@router.get("/destinations", response_model=list[DestinationRead])
def list_my_destinations(
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> list[DestinationRead]:
    """The roles the student has added, oldest first, with the résumé each one uses."""
    resumes = {resume.id: resume for resume in accounts.list_resumes(user)}
    return [
        DestinationRead(
            job_family=destination.job_family,
            resume_id=destination.resume_id,
            original_filename=resumes[destination.resume_id].original_filename,
            created_at=destination.created_at,
        )
        for destination in accounts.list_destinations(user)
    ]


@router.put("/destinations/{job_family}", response_model=ResumeRead)
def set_my_destination(
    job_family: JobFamily,
    data: DestinationUpdate,
    user: User = Depends(get_current_db_user),
    accounts: AccountService = Depends(get_account_service),
) -> ResumeRead:
    """Add a role, or change the résumé it uses. 404 if the résumé isn't one of the student's."""
    resume = accounts.use_resume(user, job_family, data.resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résumé not found")
    return _resume_read(resume)
