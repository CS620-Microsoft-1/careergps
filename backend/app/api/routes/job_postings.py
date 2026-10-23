"""One JD analysis endpoint: read the source, return and export the result locally."""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_job_analysis_pipeline, require_job_analysis_admin_token
from app.schemas.job_posting_analysis import (
    JobPostingAnalysisRequest,
    JobPostingAnalysisResponse,
)
from app.services.job_posting_analysis_pipeline import (
    JobPostingAnalysisPipeline,
    JobPostingAnalysisStateError,
    JobPostingNotFoundError,
    JobPostingSourceReadOnlyError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/job-postings", tags=["job-postings"])


@contextmanager
def _pipeline_errors() -> Iterator[None]:
    try:
        yield
    except JobPostingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The source job posting was not found.",
        ) from None
    except JobPostingAnalysisStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The local analysis lease was lost or its state changed. Retry this request.",
        ) from None
    except (sqlite3.Error, OSError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local job analysis storage is unavailable.",
        ) from None
    except (SQLAlchemyError, JobPostingSourceReadOnlyError) as error:
        # SQL/driver exception messages may contain connection details or JD content.
        logger.error("Job posting database request failed (%s).", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The job posting database is unavailable.",
        ) from None


@router.post(
    "/{job_posting_id}/analyze",
    response_model=JobPostingAnalysisResponse,
    status_code=status.HTTP_200_OK,
    responses={202: {"description": "Another local worker is already processing this posting."}},
    dependencies=[Depends(require_job_analysis_admin_token)],
)
def request_job_analysis(
    job_posting_id: UUID,
    response: Response,
    body: JobPostingAnalysisRequest | None = Body(default=None),
    pipeline: JobPostingAnalysisPipeline = Depends(get_job_analysis_pipeline),
) -> dict:
    """Analyze one JP; cloud data stays read-only and output is a local JSON export."""
    with _pipeline_errors():
        result = pipeline.analyze(job_posting_id, force=body.force if body else False)
    if result["status"] in ("queued", "running"):
        response.status_code = status.HTTP_202_ACCEPTED
    return result

