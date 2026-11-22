"""Permanently delete a student's account (hard delete, no grace period).

Deleting the Supabase Auth user removes everything in the database: users.id references auth.users
ON DELETE CASCADE, and résumés, destinations, courses, plan items and skill-gap runs/results all
cascade from users or résumés. Local result files are outside the database, so they are removed
afterwards with the run ids read beforehand.

Order matters: if the Supabase call fails nothing has changed and the student can retry. After it
succeeds, the user's queued/running skill-gap runs are cancelled (so their worker writes nothing
more), then local files are removed. Failures in those last two steps only log a warning: the
account is already gone and the files are recomputable caches that can be swept later.
"""
from collections.abc import Callable, Iterable
import logging
from uuid import UUID

import httpx2
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.skill_gap import SkillGapRunRecord
from app.services.local_user_data import delete_local_user_data
from app.services.skill_gaps.runs import forget_user_runs

logger = logging.getLogger(__name__)

ADMIN_TIMEOUT_SECONDS = 10.0


class AccountDeletionNotConfigured(RuntimeError):
    """SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set."""


class AccountDeletionFailed(RuntimeError):
    """Supabase did not delete the user; nothing was changed."""


def delete_account(
    db: Session,
    user_id: UUID,
    settings: Settings,
    *,
    client: httpx2.Client | None = None,
    delete_local: Callable[[UUID, Iterable[UUID]], object] = delete_local_user_data,
    forget_runs: Callable[[UUID], object] = forget_user_runs,
) -> None:
    base_url = (settings.supabase_url or "").rstrip("/")
    key = settings.supabase_service_role_key.get_secret_value() if settings.supabase_service_role_key else ""
    if not base_url or not key:
        raise AccountDeletionNotConfigured("Account deletion is not configured.")
    user_id = UUID(str(user_id))

    # Read the run ids now: the cascade removes these rows. End the read transaction so no
    # pooler connection is held during the HTTP call.
    run_ids = list(db.scalars(select(SkillGapRunRecord.id).where(SkillGapRunRecord.user_id == user_id)))
    db.rollback()

    _delete_auth_user(base_url, key, user_id, client)

    # Before the files: a cancelled worker stops writing, and removes what it wrote when it ends.
    try:
        forget_runs(user_id)
    except Exception:
        logger.warning("Account %s deleted, but its skill-gap runs could not be cancelled", user_id,
                       exc_info=True)
    try:
        delete_local(user_id, run_ids)
    except Exception:
        logger.warning("Account %s deleted, but its local result files could not all be removed", user_id,
                       exc_info=True)
    logger.info("Deleted account %s", user_id)


def _delete_auth_user(base_url: str, key: str, user_id: UUID, client: httpx2.Client | None) -> None:
    owns_client = client is None
    client = client or httpx2.Client(timeout=ADMIN_TIMEOUT_SECONDS)
    try:
        response = client.delete(
            f"{base_url}/auth/v1/admin/users/{user_id}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
    except httpx2.HTTPError as error:
        # The message names only the error type: never the key or the request headers.
        raise AccountDeletionFailed(f"Supabase could not be reached ({type(error).__name__}).") from None
    finally:
        if owns_client:
            client.close()
    # 404: the user is already gone (a retry after a lost response), which is what was asked for.
    if response.status_code not in (200, 204, 404):
        raise AccountDeletionFailed(f"Supabase refused to delete the user (HTTP {response.status_code}).")
