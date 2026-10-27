"""Saved resources per student and role, kept as local JSON like the skill-gap runs.

One file per user under local_results/plans. Moving this to a database table needs a migration;
until then the same single-host limits as docs/testing/SKILL_GAP_WEB_LOCAL.md apply.
"""
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.core.config import BACKEND_ROOT
from app.services.skill_gaps.storage import load, save_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalPlanStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path(self, user_id: UUID) -> Path:
        # UUID formatting keeps the name to hex and dashes.
        return self.directory / f"{UUID(str(user_id))}.json"

    def _read(self, user_id: UUID) -> dict:
        path = self._path(user_id)
        return load(path) if path.exists() else {"families": {}}

    def items(self, user_id: UUID, family: str) -> list[dict]:
        with self._lock:
            saved = self._read(user_id)["families"].get(family, {})
        return [{"resource_id": key, **value} for key, value in saved.items()]

    def set_status(self, user_id: UUID, family: str, resource_id: str, status: str) -> dict:
        with self._lock:
            data = self._read(user_id)
            saved = data["families"].setdefault(family, {})
            item = saved.get(resource_id) or {"saved_at": _now()}
            item["status"] = status
            item["done_at"] = (item.get("done_at") or _now()) if status == "done" else None
            saved[resource_id] = item
            save_json(self._path(user_id), data)
        return {"resource_id": resource_id, **item}

    def remove(self, user_id: UUID, family: str, resource_id: str) -> None:
        with self._lock:
            data = self._read(user_id)
            if data["families"].get(family, {}).pop(resource_id, None) is not None:
                save_json(self._path(user_id), data)


@lru_cache
def get_plan_store() -> LocalPlanStore:
    return LocalPlanStore(BACKEND_ROOT / "local_results" / "plans")
