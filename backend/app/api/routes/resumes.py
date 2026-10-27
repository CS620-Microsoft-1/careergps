from __future__ import annotations

import json
import logging
import queue
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

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
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _display_name(filename: str | None, suffix: str) -> str:
    name = PureWindowsPath(PurePosixPath(filename or "").name).name.strip()
    return (name or f"resume{suffix}")[:255]


def _read_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """Return the upload's bytes, real file type and display name, or raise 413/422/415."""
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
    except UnsupportedResumeError as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    return data, suffix, _display_name(file.filename, suffix)


def _error_response(error: Exception) -> tuple[int, str] | None:
    """The HTTP status and message for a pipeline failure, or None for an unexpected error."""
    if isinstance(error, UnsupportedResumeError):
        return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(error)
    if isinstance(error, InvalidResumeError):
        return status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
    if isinstance(error, OCRProcessingError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, str(error)
    if isinstance(error, ClassificationValidationError):
        return status.HTTP_502_BAD_GATEWAY, f"The Foundry Agent returned an invalid result: {error}"
    if isinstance(error, FoundryAgentError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, str(error)
    return None


def _analyze(
    pipeline: ResumePipeline, data: bytes, suffix: str, filename: str, on_step=None
) -> ResumeAnalysis:
    with tempfile.TemporaryDirectory(prefix="careergps_resume_") as directory:
        temporary_path = Path(directory) / f"upload{suffix}"
        temporary_path.write_bytes(data)
        result = pipeline.analyze(temporary_path, suffix, filename, on_step=on_step)
    return ResumeAnalysis.model_validate(result)


# Logged-in users only (SPEC-001 §8): each call costs a Foundry Agent run. Not get_current_db_user:
# onboarding analyzes the résumé before the users row exists.
@router.post("/analyze", response_model=ResumeAnalysis, dependencies=[Depends(get_current_user)])
def analyze_resume(
    file: UploadFile = File(...),
    pipeline: ResumePipeline = Depends(get_resume_pipeline),
) -> ResumeAnalysis:
    """Temporarily extract and classify one résumé; persist neither file nor result."""
    data, suffix, filename = _read_upload(file)
    try:
        return _analyze(pipeline, data, suffix, filename)
    except Exception as error:
        response = _error_response(error)
        if response is None:
            raise
        raise HTTPException(status_code=response[0], detail=response[1]) from error


def _event_line(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _stream_analysis(pipeline: ResumePipeline, data: bytes, suffix: str, filename: str) -> Iterator[str]:
    """Run the pipeline in a worker thread and yield each step event as it happens."""
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def on_step(step: str, step_status: str, detail: dict[str, Any] | None = None) -> None:
        events.put({"type": "step", "step": step, "status": step_status, "detail": detail or {}})

    def run() -> None:
        try:
            result = _analyze(pipeline, data, suffix, filename, on_step=on_step)
            events.put({"type": "result", "data": result.model_dump(mode="json")})
        except Exception as error:
            response = _error_response(error)
            if response is None:
                logger.exception("Résumé analysis failed unexpectedly")
                response = (status.HTTP_500_INTERNAL_SERVER_ERROR, "Something went wrong while reading the résumé.")
            events.put({"type": "error", "status": response[0], "detail": response[1]})
        finally:
            events.put(None)

    # The upload has arrived and passed the size and file-type checks.
    yield _event_line(
        {
            "type": "step",
            "step": "upload",
            "status": "done",
            "detail": {"filename": filename, "file_type": suffix.lstrip("."), "bytes": len(data)},
        }
    )
    # If the student leaves, the thread still finishes (the Agent call can't be cancelled) and
    # deletes the temporary file.
    threading.Thread(target=run, name="resume-analysis", daemon=True).start()
    while (event := events.get()) is not None:
        yield _event_line(event)


@router.post("/analyze/stream", dependencies=[Depends(get_current_user)])
def analyze_resume_stream(
    file: UploadFile = File(...),
    pipeline: ResumePipeline = Depends(get_resume_pipeline),
) -> StreamingResponse:
    """Like /analyze, but streams NDJSON: one line per step, then a "result" or "error" line.

    Size and file-type problems are still plain 413/422/415 responses. Failures after streaming
    starts arrive as {"type": "error", "status": ..., "detail": ...} because the 200 is already sent.
    """
    data, suffix, filename = _read_upload(file)
    return StreamingResponse(
        _stream_analysis(pipeline, data, suffix, filename),
        media_type="application/x-ndjson",
        # Ask proxies not to buffer, so each line reaches the browser right away.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
