from collections.abc import Iterator
from secrets import compare_digest
import sqlite3

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.api.resume_deps import get_resume_pipeline
from app.services.job_posting_analysis_agent import AGENT_VERSION, FoundryJobPostingAnalysisService
from app.services.job_posting_analysis_pipeline import (
    JobPostingAnalysisPipeline,
    ReadOnlyJobPostingSource,
)
from app.services.local_job_analysis_store import LocalJobAnalysisStore


def get_db() -> Iterator[Session]:
    """Give each request its own session and always close it, returning the connection to the pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_job_analysis_token_header = APIKeyHeader(
    name="X-Job-Analysis-Token", scheme_name="JobAnalysisAdminToken", auto_error=False
)


def require_job_analysis_admin_token(
    token: str | None = Depends(_job_analysis_token_header),
    settings: Settings = Depends(get_settings),
) -> None:
    configured = settings.job_analysis_admin_token
    expected = configured.get_secret_value() if configured is not None else ""
    if not expected.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job analysis submission is not enabled on this backend.",
        )
    if token is None or not compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid job analysis management token.",
            headers={"WWW-Authenticate": "APIKey"},
        )


def get_job_analysis_pipeline() -> JobPostingAnalysisPipeline:
    settings = get_settings()
    agent = FoundryJobPostingAnalysisService(
        endpoint=settings.job_analysis_project_endpoint,
        timeout_seconds=settings.job_analysis_timeout_seconds,
    )
    directory = settings.job_analysis_local_dir
    if not directory.is_absolute():
        directory = BACKEND_ROOT / directory
    # Always isolate output contracts, including when .env overrides the base path.
    # Older queues/results remain untouched and are never served as v13 output.
    directory = directory / f"v{AGENT_VERSION}"
    try:
        store = LocalJobAnalysisStore(directory)
    except (sqlite3.Error, OSError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local job analysis storage is unavailable.",
        ) from None
    return JobPostingAnalysisPipeline(ReadOnlyJobPostingSource(SessionLocal), store, agent)
