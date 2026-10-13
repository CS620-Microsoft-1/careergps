from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.config import get_settings
from app.services.foundry_agent import FoundryResumeAgentService
from app.services.resume_pipeline import ResumePipeline


def get_db() -> Iterator[Session]:
    """Give each request its own session and always close it, returning the connection to the pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_resume_pipeline() -> ResumePipeline:
    """Build the stateless pipeline; no uploaded file or result is persisted."""
    settings = get_settings()
    agent = FoundryResumeAgentService(
        endpoint=settings.foundry_project_endpoint,
        agent_name=settings.foundry_agent_name,
    )
    return ResumePipeline(agent)
