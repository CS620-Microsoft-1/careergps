from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, get_resume_pipeline
from app.schemas.resume import ResumeAnalysis
from app.services.foundry_agent import ClassificationValidationError, FoundryAgentError
from app.services.resume_extraction import (
    InvalidResumeError,
    OCRProcessingError,
    UnsupportedResumeError,
    detect_file_type,
)
from app.services.resume_pipeline import ResumePipeline

router = APIRouter(prefix="/resumes", tags=["resumes"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _display_name(filename: str | None, suffix: str) -> str:
    name = PureWindowsPath(PurePosixPath(filename or "").name).name.strip()
    return (name or f"resume{suffix}")[:255]


# Logged-in users only (SPEC-001 §8): each call costs a Foundry Agent run. Not get_current_db_user:
# onboarding analyzes the résumé before the users row exists.
@router.post("/analyze", response_model=ResumeAnalysis, dependencies=[Depends(get_current_user)])
def analyze_resume(
    file: UploadFile = File(...),
    pipeline: ResumePipeline = Depends(get_resume_pipeline),
) -> ResumeAnalysis:
    """Temporarily extract and classify one résumé; persist neither file nor result."""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File must be 10 MB or smaller.",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The file is empty.")

    try:
        suffix = detect_file_type(data)
        filename = _display_name(file.filename, suffix)
        with tempfile.TemporaryDirectory(prefix="careergps_resume_") as directory:
            temporary_path = Path(directory) / f"upload{suffix}"
            temporary_path.write_bytes(data)
            result = pipeline.analyze(temporary_path, suffix, filename)
        return ResumeAnalysis.model_validate(result)
    except UnsupportedResumeError as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    except InvalidResumeError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    except OCRProcessingError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ClassificationValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The Foundry Agent returned an invalid result: {error}",
        ) from error
    except FoundryAgentError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
