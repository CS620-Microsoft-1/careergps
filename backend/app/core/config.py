from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """App settings, read from environment variables and backend/.env (env vars win)."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    # Transaction pooler (port 6543): the app holds a pooler connection only while a transaction runs.
    database_url: str
    # Session pooler (port 5432), for Alembic only. Falls back to database_url when unset.
    migration_database_url: str | None = None
    # Comma-separated list of frontend origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:3000"
    # Supabase project URL (https://<project-ref>.supabase.co). Needed to verify login tokens.
    supabase_url: str | None = None
    # Only for projects still on the legacy shared JWT secret (HS256). Leave unset with signing keys.
    supabase_jwt_secret: str | None = None

    # Existing Microsoft Foundry resume-classification Agent. Authentication uses
    # DefaultAzureCredential (Azure CLI locally; managed identity when deployed).
    foundry_project_endpoint: str | None = None
    foundry_agent_name: str | None = None

    resources_project_endpoint: str | None = None
    resources_agent_name: str = "resources-agent"
    # Independent endpoint for the existing job-analysis-agent, pinned to version 13.
    job_analysis_project_endpoint: str | None = None
    # Local storage base; the JD factory appends v13 to isolate older output formats.
    # Source database access stays read-only.
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


class SkillGapSettings(BaseSettings):
    """Skill Gap Agent settings; analysis results stay in backend-local JSON."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    skill_gap_foundry_project_endpoint: str | None = None
    skill_gap_foundry_agent_name: str | None = None


class CertificationSettings(BaseSettings):
    """Certification recommendation Agent; without it, recommendations fall back to gap ranking."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    certification_foundry_project_endpoint: str | None = None
    certification_foundry_agent_name: str | None = None
