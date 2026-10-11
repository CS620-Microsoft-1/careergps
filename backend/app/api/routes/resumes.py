import uuid
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_db_user,
    get_db,
    get_llm_client,
    get_session_factory,
    get_storage,
)
from app.models import User
from app.schemas.resume import ResumeConfirm, ResumeRead, ResumeSummary
from app.services import resumes
from app.services.llm import LLMClient
from app.services.parsing import run_parse_job
from app.services.pdf import InvalidPdfError, NotPdfError
from app.services.storage import FileStorage, StorageError

router = APIRouter(prefix="/resumes", tags=["resumes"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _owned(db: Session, user: User, resume_id: uuid.UUID):
    try:
        return resumes.get_owned(db, user, resume_id)
    except resumes.ResumeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résumé not found")


def _conflict(error: resumes.ResumeConflictError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ResumeSummary)
def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    llm: LLMClient | None = Depends(get_llm_client),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
):
    """Store a PDF résumé and start parsing it. Poll GET /resumes/{id} for the result."""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File must be 10 MB or smaller."
        )
    try:
        resume = resumes.upload(db, storage, user, file.filename, data)
    except NotPdfError as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error))
    except InvalidPdfError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    except resumes.ResumeConflictError as error:
        raise _conflict(error)
    except StorageError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not store the file. Try again."
        )

    background_tasks.add_task(run_parse_job, resume.id, session_factory, storage, llm)
    return resume


@router.get("/{resume_id}", response_model=ResumeRead)
def read_resume(
    resume_id: uuid.UUID,
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    return _owned(db, user, resume_id)


@router.post("/{resume_id}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=ResumeSummary)
def retry_resume(
    resume_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    llm: LLMClient | None = Depends(get_llm_client),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
):
    """Parse a failed résumé again (same file)."""
    try:
        resume = resumes.retry(db, _owned(db, user, resume_id))
    except resumes.ResumeConflictError as error:
        raise _conflict(error)
    background_tasks.add_task(run_parse_job, resume.id, session_factory, storage, llm)
    return resume


@router.post("/{resume_id}/confirm", response_model=ResumeRead)
def confirm_resume(
    resume_id: uuid.UUID,
    data: ResumeConfirm,
    user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Save the user-checked data to the profile tables. P0: a confirmed résumé can't be replaced."""
    try:
        return resumes.confirm(db, user, _owned(db, user, resume_id), data)
    except resumes.ResumeConflictError as error:
        raise _conflict(error)
