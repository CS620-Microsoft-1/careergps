from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """App settings, read from environment variables and backend/.env (env vars win)."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    database_url: str
    # Comma-separated list of frontend origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:3000"
    # Supabase project URL (https://<project-ref>.supabase.co). Needed to verify login tokens.
    supabase_url: str | None = None
    # Only for projects still on the legacy shared JWT secret (HS256). Leave unset with signing keys.
    supabase_jwt_secret: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
