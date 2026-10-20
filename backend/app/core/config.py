from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """App settings, read from environment variables and backend/.env (env vars win)."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    database_url: str
    # Comma-separated list of frontend origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:3000"
    # Existing Microsoft Foundry resume-classification Agent. Authentication uses
    # DefaultAzureCredential (Azure CLI locally; managed identity when deployed).
    foundry_project_endpoint: str | None = None
    foundry_agent_name: str | None = None
    # Independent endpoint for the existing job-analysis-agent, pinned to version 10.
    job_analysis_project_endpoint: str | None = None
    # Analysis queues and exported JSON stay local; source database access is read-only.
    job_analysis_local_dir: Path = BACKEND_ROOT / "local_exports" / "job_analyses"
    # Server-side management token for the analysis submission endpoint only.
    job_analysis_admin_token: SecretStr | None = None
    job_analysis_timeout_seconds: float = Field(
        default=600.0, gt=0, allow_inf_nan=False
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
