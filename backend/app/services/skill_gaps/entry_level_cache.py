"""Owner-isolated cache for exact entry-level Agent inputs."""

from copy import deepcopy
from pathlib import Path
from typing import Callable
from uuid import UUID

from .branch_cache import CacheHit, _RUN_ID, _digest
from .skill_groups import GROUPS
from .storage import load, save_json


ENTRY_LEVEL_BRANCH_CACHE_VERSION = "entry-level-exact-input-cache.v1"


def _cacheable(output: dict, validation: dict, payload: dict) -> bool:
    skills = set(payload["evidence_scope"]["assigned_skill_ids"])
    rows = validation["skills"]
    body = output["result"]
    return (
        output["task"] == payload["task"]
        and body["job_family"] == payload["job_family"]
        and set(body) == skills | {"job_family"}
        and not validation["global_errors"]
        and validation["status"] in {"passed", "partial"}
        and set(rows) == skills
        and all(row["status"] in {"passed", "needs_confirmation"} for row in rows.values())
    )


class EntryLevelBranchCache:
    """Persist only valid responses, and revalidate on every exact-input hit."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory).resolve() / ENTRY_LEVEL_BRANCH_CACHE_VERSION

    def _identity(self, *, owner: str, resume_id: str, branch: str, payload: dict,
                  binding: dict, dependencies: dict) -> dict:
        owner, resume_id = str(UUID(str(owner))), str(UUID(str(resume_id)))
        if (branch not in GROUPS or payload["evidence_scope"]["branch"] != branch
                or (payload.get("resume_id") is not None and str(payload["resume_id"]) != resume_id)
                or not isinstance(binding, dict) or not binding or not isinstance(dependencies, dict)):
            raise ValueError("Incomplete entry-level cache identity")
        return {
            "cache_version": ENTRY_LEVEL_BRANCH_CACHE_VERSION, "owner": owner, "branch": branch,
            "input_sha256": _digest(payload), "binding_sha256": _digest(binding),
            "dependencies_sha256": _digest(dependencies),
        }

    def key(self, *, owner: str, resume_id: str, branch: str, payload: dict,
            binding: dict, dependencies: dict) -> str:
        return _digest(self._identity(owner=owner, resume_id=resume_id, branch=branch, payload=payload,
                                      binding=binding, dependencies=dependencies))

    def _path(self, identity: dict, key: str) -> Path:
        # The complete owner is already part of the key and checked on reads.
        # A short directory hash leaves room for atomic temp names on Windows.
        namespace = _digest({"owner": identity["owner"]})[:24]
        return self.directory / namespace / (key + ".json")

    def store(self, *, owner: str, resume_id: str, branch: str, payload: dict,
              binding: dict, dependencies: dict, output: dict, validation: dict,
              source_run_id: str, artifacts: dict | None = None,
              original_model_calls: int = 1) -> bool:
        try:
            if (not _RUN_ID.fullmatch(source_run_id) or type(original_model_calls) is not int
                    or original_model_calls < 0 or (artifacts is not None and not isinstance(artifacts, dict))
                    or not _cacheable(output, validation, payload)):
                return False
            identity = self._identity(owner=owner, resume_id=resume_id, branch=branch, payload=payload,
                                      binding=binding, dependencies=dependencies)
            key = _digest(identity)
            value = {
                "identity": identity, "key": key, "output": output, "validation": validation,
                "source_run_id": source_run_id, "source_resume_id": str(UUID(str(resume_id))),
                "original_model_calls": original_model_calls, "artifacts": artifacts or {},
            }
            save_json(self._path(identity, key), {"checksum": _digest(value), "value": value})
            return True
        except Exception:
            # Cache storage is optional, including serialization and disk failures.
            return False

    def lookup(self, *, owner: str, resume_id: str, branch: str, payload: dict,
               binding: dict, dependencies: dict,
               validate: Callable[[dict, dict], dict]) -> CacheHit | None:
        try:
            identity = self._identity(owner=owner, resume_id=resume_id, branch=branch, payload=payload,
                                      binding=binding, dependencies=dependencies)
            key = _digest(identity)
            entry = load(self._path(identity, key))
            value = entry["value"]
            if (entry["checksum"] != _digest(value) or value["identity"] != identity
                    or value["key"] != key or not _RUN_ID.fullmatch(value["source_run_id"])
                    or type(value["original_model_calls"]) is not int or value["original_model_calls"] < 0
                    or str(UUID(value["source_resume_id"])) != value["source_resume_id"]
                    or not isinstance(value["artifacts"], dict)):
                return None
            output = value["output"]
            checks = validate(deepcopy(output), deepcopy(payload))
            if checks != value["validation"] or not _cacheable(output, checks, payload):
                return None
            return CacheHit(key=key, output=output, validation=checks,
                            source_run_id=value["source_run_id"], source_resume_id=value["source_resume_id"],
                            original_model_calls=value["original_model_calls"],
                            artifacts=value["artifacts"], id_remapping={})
        except Exception:
            # Corrupt, unavailable, and incompatible entries are ordinary misses.
            return None
