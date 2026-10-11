import logging
from collections.abc import Callable, Iterator
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    AuthenticatedUser,
    AuthError,
    AuthUnavailableError,
    SupabaseTokenVerifier,
)
from app.db.session import SessionLocal
from app.models import User
from app.services.llm import AzureOpenAIClient, LLMClient
from app.services.storage import FileStorage, SupabaseStorage

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """Give each request its own session and always close it, returning the connection to the pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> Callable[[], Session]:
    """For background jobs, which outlive the request's session."""
    return SessionLocal


@lru_cache
def _build_token_verifier(supabase_url: str, jwt_secret: str | None) -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(supabase_url, jwt_secret)


def get_token_verifier() -> SupabaseTokenVerifier:
    settings = get_settings()
    if not settings.supabase_url:
        logger.error("SUPABASE_URL is not set; cannot verify login tokens")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured"
        )
    return _build_token_verifier(settings.supabase_url, settings.supabase_jwt_secret)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: SupabaseTokenVerifier = Depends(get_token_verifier),
) -> AuthenticatedUser:
    """The Supabase account behind the request's bearer token. 401 if there is no valid token."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return verifier.verify(credentials.credentials)
    except AuthUnavailableError:
        logger.exception("Could not fetch Supabase signing keys")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication unavailable"
        )
    except AuthError as error:
        # The reason is logged, never the token itself.
        logger.info("Rejected token: %s", error)
        raise unauthorized


def get_current_db_user(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Like get_current_user, but also requires the users row from POST /me. 403 if sign-up isn't finished."""
    user = db.get(User, auth_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Finish sign-up first")
    return user


@lru_cache
def _build_storage(supabase_url: str, secret_key: str, bucket: str) -> SupabaseStorage:
    return SupabaseStorage(supabase_url, secret_key, bucket)


def get_storage() -> FileStorage:
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_secret_key):
        logger.error("SUPABASE_URL or SUPABASE_SECRET_KEY is not set; cannot store résumés")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage is not configured"
        )
    return _build_storage(settings.supabase_url, settings.supabase_secret_key, settings.resume_bucket)


@lru_cache
def _build_llm_client(endpoint: str, api_key: str, deployment: str, api_version: str) -> AzureOpenAIClient:
    return AzureOpenAIClient(endpoint, api_key, deployment, api_version)


def get_llm_client() -> LLMClient | None:
    """None when Azure OpenAI isn't configured: uploads still work, parsing fails with llm_unavailable."""
    settings = get_settings()
    values = (
        settings.azure_openai_endpoint,
        settings.azure_openai_api_key,
        settings.azure_openai_deployment,
        settings.azure_openai_api_version,
    )
    if not all(values):
        return None
    return _build_llm_client(*values)
