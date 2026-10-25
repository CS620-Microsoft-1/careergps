"""Resume-only dependency; importing it never initializes database services."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import BACKEND_ROOT
from app.services.foundry_agent import FoundryResumeAgentService
from app.services.resume_pipeline import ResumePipeline


class ResumeAgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")
    foundry_project_endpoint: str | None = None
    foundry_agent_name: str | None = None


@lru_cache
def get_resume_agent_settings() -> ResumeAgentSettings:
    return ResumeAgentSettings()


def get_resume_pipeline() -> ResumePipeline:
    settings = get_resume_agent_settings()
    return ResumePipeline(FoundryResumeAgentService(
        endpoint=settings.foundry_project_endpoint,
        agent_name=settings.foundry_agent_name,
    ))
