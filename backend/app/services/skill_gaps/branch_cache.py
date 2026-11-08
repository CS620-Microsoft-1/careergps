"""Owner-isolated branch responses with exact source identity and ID remapping.

Only generated activity/unit IDs are ignored when comparing inputs. Source text,
paths, structural kinds, context, order, and every configured dependency remain
part of the cache key. A hit is revalidated; cached uncertainty or invalid proofs
cannot become positive evidence merely because the surrounding resume changed.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
from uuid import UUID

from .sources import build_index


BRANCH_CACHE_VERSION = "scoped-evidence-cache.v2"
_BRANCHES = {"foundation", "lifecycle", "systems"}
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHAPE_ERRORS = {"invalid_record_shape", "missing_skill", "unusable_response_context",
                 "unknown_evidence_id", "invalid_source_text"}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sources(payload: dict) -> list[dict]:
    sources = payload["resume_sources"]
    if not isinstance(sources, list):
        raise ValueError("Sources must be an ordered list")
    build_index(sources)  # Reject duplicate IDs before assigning a reference map.
    paths, unit_paths = set(), set()
    for source in sources:
        path = source["path"]
        if not isinstance(path, str) or not path.startswith("/") or path in paths:
            raise ValueError("Activity paths must be unique original JSON pointers")
        paths.add(path)
        if not isinstance(source["units"], list):
            raise ValueError("Units must be an ordered list")
        for unit in source["units"]:
            unit_path = unit["path"]
            if (not isinstance(unit_path, str) or not unit_path.startswith("/")
                    or unit_path in unit_paths or not isinstance(unit["text"], str)
                    or not isinstance(unit["kind"], str)):
                raise ValueError("Units need unique original paths, text, and kinds")
            unit_paths.add(unit_path)
    return sources


def canonical_branch_payload(payload: dict) -> dict:
    """Preserve all input content except generated IDs and root resume identity."""
    sources = _sources(payload)
    scope = payload["evidence_scope"]
    if (not isinstance(scope, dict) or scope.get("branch") not in _BRANCHES
            or scope.get("activity_ids") != [source["id"] for source in sources]):
        raise ValueError("The supplied branch scope must exactly describe its sources")
    result = deepcopy(payload)
    result.pop("resume_id", None)  # Revisions share a key only within one owner.
    result["evidence_scope"].pop("activity_ids")
    for source in result["resume_sources"]:
        source.pop("id")
        for unit in source["units"]:
            unit.pop("id")
    return result


def source_id_mapping(previous: dict, current: dict) -> dict[str, dict[str, str]]:
    """Match complete ordered activities, never globally match duplicate text."""
    if canonical_branch_payload(previous) != canonical_branch_payload(current):
        raise ValueError("Branch content changed")
    activities, units = {}, {}
    for old, new in zip(_sources(previous), _sources(current)):
        activities[old["id"]] = new["id"]
        for old_unit, new_unit in zip(old["units"], new["units"]):
            units[old_unit["id"]] = new_unit["id"]
    return {"activities": activities, "units": units}


def remap_response(output: dict, mapping: dict[str, dict[str, str]]) -> dict:
    """Replace schema reference fields only; quotes/reasons/classifications stay exact."""
    remapped = deepcopy(output)
    units = mapping["units"]

    def reference(record: dict, field: str) -> None:
        if record[field] is not None:
            record[field] = units[record[field]]  # Unknown/cross-branch IDs miss.

    for skill, record in remapped["result"].items():
        if skill == "job_family":
            continue
        kind = record["kind"]
        if kind in {"knowledge", "uncertain"}:
            reference(record, "evidence_id")
        elif kind in {"practice", "limited_practice"}:
            reference(record, "operation_id")
            if record["method"] is not None:
                reference(record["method"]["proof"], "unit_id")
            if record["validation"] is not None:
                for field in ("check", "finding", "reference"):
                    proof = record["validation"][field]
                    if proof is not None:
                        reference(proof, "unit_id")
        elif kind != "absent":
            raise ValueError("Unknown record kind")
    return remapped


def _remap_validation(validation: dict, mapping: dict) -> dict:
    result = deepcopy(validation)
    for row in result["skills"].values():
        row["evidence_ids"] = [mapping["units"][value] for value in row["evidence_ids"]]
        if row.get("derived_activity_id") is not None:
            row["derived_activity_id"] = mapping["activities"][row["derived_activity_id"]]
        for name in ("proof_spans", "reported_value_spans"):
            for span in row.get(name, []):
                if "unit_id" in span:
                    span["unit_id"] = mapping["units"][span["unit_id"]]
    return result


def _cacheable(output: dict, validation: dict, payload: dict) -> bool:
    skills = {skill["skill_id"] for skill in payload["core_skills"]}
    body = output.get("result")
    if (output.get("task") != payload["task"] or not isinstance(body, dict)
            or set(body) != skills | {"job_family"}
            or body["job_family"] != payload["job_family"]
            or validation.get("global_errors") or validation.get("status") not in {"passed", "partial"}
            or set(validation.get("skills", {})) != skills):
        return False
    for skill in skills:
        if not isinstance(body[skill], dict):
            return False
        row = validation["skills"][skill]
        if (row.get("status") not in {"passed", "needs_confirmation"}
                or any(error.get("code") in _SHAPE_ERRORS for error in row.get("errors", []))):
            return False
    return True


@dataclass(frozen=True)
class CacheHit:
    key: str
    output: dict
    validation: dict
    source_run_id: str
    source_resume_id: str
    original_model_calls: int
    artifacts: dict
    id_remapping: dict


class BranchCache:
    """Optional local persistence; corrupt or incompatible entries are cache misses."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory).resolve()

    def _identity(self, *, owner: str, resume_id: str, branch: str, payload: dict,
                  binding: dict, dependencies: dict) -> dict:
        owner, resume_id = str(UUID(str(owner))), str(UUID(str(resume_id)))
        if (branch not in _BRANCHES or payload.get("evidence_scope", {}).get("branch") != branch
                or str(payload.get("resume_id")) != resume_id
                or not isinstance(binding, dict) or not binding or not isinstance(dependencies, dict)):
            raise ValueError("Incomplete branch cache identity")
        return {"cache_version": BRANCH_CACHE_VERSION, "owner": owner,
                "branch": branch, "input": canonical_branch_payload(payload),
                "binding": deepcopy(binding), "dependencies": deepcopy(dependencies)}

    def key(self, *, owner: str, resume_id: str, branch: str, payload: dict,
            binding: dict, dependencies: dict) -> str:
        return _digest(self._identity(owner=owner, resume_id=resume_id, branch=branch,
            payload=payload, binding=binding, dependencies=dependencies))

    def _path(self, identity: dict, key: str) -> Path:
        namespace = _digest({"owner": identity["owner"]})
        return self.directory / BRANCH_CACHE_VERSION / namespace / (key + ".json")

    def store(self, *, owner: str, resume_id: str, branch: str, payload: dict,
              binding: dict, dependencies: dict, output: dict, validation: dict,
              source_run_id: str, artifacts: dict | None = None,
              original_model_calls: int = 1) -> bool:
        temp_path = None
        try:
            if (not _RUN_ID.fullmatch(source_run_id) or type(original_model_calls) is not int
                    or original_model_calls < 0 or (artifacts is not None and not isinstance(artifacts, dict))
                    or not _cacheable(output, validation, payload)):
                return False
            identity = self._identity(owner=owner, resume_id=resume_id, branch=branch,
                payload=payload, binding=binding, dependencies=dependencies)
            mapping = source_id_mapping(payload, payload)
            remap_response(output, mapping)  # Unknown references are never persisted.
            _remap_validation(validation, mapping)
            key = _digest(identity)
            value = {"identity": identity, "key": key, "payload": deepcopy(payload),
                     "output": deepcopy(output), "validation": deepcopy(validation),
                     "source_run_id": source_run_id, "source_resume_id": str(UUID(str(resume_id))),
                     "original_model_calls": original_model_calls,
                     "artifacts": deepcopy(artifacts or {})}
            entry = {"checksum": _digest(value), "value": value}
            target = self._path(identity, key)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="wb", prefix=key + "-", suffix=".tmp",
                                             dir=target.parent, delete=False) as handle:
                temp_path = Path(handle.name)
                handle.write(_canonical(entry))
            os.replace(temp_path, target)
            temp_path = None
            return True
        except Exception:
            # Cache storage is optional and must never invalidate a completed run.
            return False
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def lookup(self, *, owner: str, resume_id: str, branch: str, payload: dict,
               binding: dict, dependencies: dict,
               validate: Callable[[dict, dict], dict]) -> CacheHit | None:
        try:
            identity = self._identity(owner=owner, resume_id=resume_id, branch=branch,
                payload=payload, binding=binding, dependencies=dependencies)
            key = _digest(identity)
            entry = json.loads(self._path(identity, key).read_text(encoding="utf-8"))
            value = entry["value"]
            if (entry["checksum"] != _digest(value) or value["identity"] != identity
                    or value["key"] != key or not _RUN_ID.fullmatch(value["source_run_id"])
                    or type(value["original_model_calls"]) is not int or value["original_model_calls"] < 0
                    or str(UUID(value["source_resume_id"])) != value["source_resume_id"]
                    or str(value["payload"].get("resume_id")) != value["source_resume_id"]
                    or not isinstance(value["artifacts"], dict)
                    or canonical_branch_payload(value["payload"]) != identity["input"]):
                return None
            previous_checks = validate(deepcopy(value["output"]), deepcopy(value["payload"]))
            if (previous_checks != value["validation"]
                    or not _cacheable(value["output"], previous_checks, value["payload"])):
                return None
            mapping = source_id_mapping(value["payload"], payload)
            output = remap_response(value["output"], mapping)
            checks = validate(deepcopy(output), deepcopy(payload))
            if (checks != _remap_validation(previous_checks, mapping)
                    or not _cacheable(output, checks, payload)):
                return None
            return CacheHit(key=key, output=output, validation=checks,
                source_run_id=value["source_run_id"], source_resume_id=value["source_resume_id"],
                original_model_calls=value["original_model_calls"],
                artifacts=deepcopy(value["artifacts"]), id_remapping=mapping)
        except Exception:
            return None
