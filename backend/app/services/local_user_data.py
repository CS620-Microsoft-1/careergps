"""Remove everything one user left in backend/local_results (account deletion).

The database cascade from auth.users cannot reach these files, so account deletion calls this after
the user is gone. What is kept locally, and how it is named:

- plans/<user uuid>.json                                   saved resources (LocalPlanStore)
- web_skill_gaps/<run id>/                                 each skill-gap run's inputs and Agent output
- web_skill_gaps/_branch_cache/.../<hash of user id>/      cached Agent responses (both cache formats)
- project_recommendations/<run id>.json                    project picks per run
- certifications/<run id>.json, action_plans/<run id>/     no longer written; removed if still there

Run ids must be collected from skill_gap_runs before the user is deleted. Every id is validated
before any path is built, so a bad value raises ValueError and removes nothing.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import shutil
from uuid import UUID

from app.core.config import BACKEND_ROOT
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.skill_gaps.branch_cache import BranchCache
from app.services.skill_gaps.entry_level_cache import EntryLevelBranchCache
from app.services.skill_gaps.run_store import delete_run_folders

LOCAL_RESULTS_ROOT = BACKEND_ROOT / "local_results"


@dataclass(frozen=True)
class LocalDeletionReport:
    """How many entries were removed from each place (useful in tests and logs; no personal data)."""

    plan_files: int = 0
    run_folders: int = 0
    branch_cache_folders: int = 0
    run_files: int = 0


def _run_hex(value: object) -> str:
    # Accepts a UUID or its 32-hex / dashed form; anything else is rejected.
    try:
        return UUID(str(value)).hex
    except ValueError:
        raise ValueError("Invalid run id") from None


def _remove(path: Path) -> bool:
    if path.is_dir():
        shutil.rmtree(path)
        return True
    if path.exists():
        path.unlink()
        return True
    return False


def delete_local_user_data(user_id: UUID | str, run_ids: Iterable[UUID | str],
                           root: Path = LOCAL_RESULTS_ROOT) -> LocalDeletionReport:
    try:
        user = UUID(str(user_id))
    except ValueError:
        raise ValueError("Invalid user id") from None
    runs = sorted({_run_hex(run_id) for run_id in run_ids})
    root = Path(root).resolve()

    # The app-wide plan store shares its lock with live requests; a test root gets its own store.
    plans = get_plan_store() if root == LOCAL_RESULTS_ROOT.resolve() else LocalPlanStore(root / "plans")
    plan_files = int(plans.delete_user(user))

    skill_gaps = root / "web_skill_gaps"
    run_folders = delete_run_folders(skill_gaps, runs)

    cache_dir = skill_gaps / "_branch_cache"
    branch_cache_folders = sum(int(cache.delete_owner(str(user)))
                               for cache in (BranchCache(cache_dir), EntryLevelBranchCache(cache_dir)))

    run_files = 0
    for run in runs:
        for path in (root / "project_recommendations" / f"{run}.json",
                     root / "certifications" / f"{run}.json",
                     root / "action_plans" / run):
            run_files += int(_remove(path))

    return LocalDeletionReport(plan_files, run_folders, branch_cache_folders, run_files)
