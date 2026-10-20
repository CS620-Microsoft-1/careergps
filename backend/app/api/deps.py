import logging
from collections.abc import Iterator
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
from app.services.accounts import AccountService
from app.services.foundry_agent import FoundryResumeAgentService
from app.services.resume_pipeline import ResumePipeline

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """Give each request its own session and always close it, returning the connection to the pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        # The reason is logged, never the token itself. Warning, so it shows in uvicorn's console.
        logger.warning("Rejected token: %s", error)
        raise unauthorized


def get_account_service(db: Session = Depends(get_db)) -> AccountService:
    return AccountService(db)


def get_current_db_user(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    accounts: AccountService = Depends(get_account_service),
) -> User:
    """Like get_current_user, but also requires the users row, which onboarding creates (POST /me).
    403 until then."""
    user = accounts.get_user(auth_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Finish onboarding first")
    return user


def get_resume_pipeline() -> ResumePipeline:
    """Build the stateless pipeline; no uploaded file or result is persisted."""
    settings = get_settings()
    agent = FoundryResumeAgentService(
        endpoint=settings.foundry_project_endpoint,
        agent_name=settings.foundry_agent_name,
    )
    return ResumePipeline(agent)
