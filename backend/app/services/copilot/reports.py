"""Read existing, owner-scoped Skill Gap artifacts without starting workers or writing.

This adapter describes the saved report's generation/version. It does not consult
cloud Agent versions or promise that an older report uses the current algorithm.
"""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from fastapi import HTTPException

from app.core.config import BACKEND_ROOT
from app.services.copilot.readonly import ResumeSnapshot, canonical_hash
from app.services.skill_gaps.schema import SCHEMA_NAME

_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_REPORT_CHARACTERS = 80_000
_TOP_FIELDS = ("policy_version", "calibration_status", "job_family", "metric", "core_skill_count",
               "module_count", "demand_snapshot_fingerprint", "priority_order", "unscored_skill_ids",
               "limitations", "mechanical_integrity_checked", "exact_quotes_checked",
               "semantic_evidence_verified", "agent_output_verified", "base_numeric_rubric",
               "source_lookup_scope", "unresolved_display_sources")
_SKILL_FIELDS = ("skill_id", "skill_name", "module_id", "module_name", "resume_evidence_strength",
                 "skill_gap", "skill_gap_grade", "demand", "demand_weight", "priority",
                 "calculation_state", "scoring_breakdown", "agent_assessment", "local_reference_check",
                 "evidence_verification")


def _timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs a timezone")
    return parsed


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("Invalid JSON number")


def _read_json(path: Path, *, limit: int) -> dict:
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected an ordinary artifact file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Expected an ordinary artifact file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Artifact is too large")
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_json_object,
                       parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _validate_state(state: dict, identifier: str) -> None:
    if state.get("id") != identifier or state.get("status") not in {"queued", "running", "completed", "failed"}:
        raise ValueError("Invalid run identity or status")
    for name in ("user_id", "resume_id"):
        if str(UUID(state[name])) != state[name]:
            raise ValueError("Invalid canonical identity")
    if not isinstance(state.get("resume_hash"), str) or not _HASH.fullmatch(state["resume_hash"]):
        raise ValueError("Invalid resume hash")
    fingerprint = state.get("calculation_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint or len(fingerprint) > 200:
        raise ValueError("Missing report version")
    expected = canonical_hash({"user_id": state["user_id"], "resume_id": state["resume_id"],
                               "resume_hash": state["resume_hash"], "job_family": state["job_family"],
                               "contract": SCHEMA_NAME, "fingerprint": fingerprint})
    if state.get("cache_key") != expected:
        raise ValueError("Run ownership/content key does not match")
    created = _timestamp(state["created_at"])
    if state["status"] == "completed" and _timestamp(state["completed_at"]) < created:
        raise ValueError("Invalid report completion time")


def _project_report(report: dict) -> dict:
    skills = report.get("skills")
    if not isinstance(skills, list) or not skills or len(skills) > 100:
        raise ValueError("Invalid saved skills")
    identifiers = []
    selected = []
    for row in skills:
        if not isinstance(row, dict):
            raise ValueError("Invalid saved skill")
        identifier = row.get("skill_id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Invalid or duplicate saved skill")
        identifiers.append(identifier)
        if not isinstance(row.get("skill_name"), str) or not isinstance(row.get("calculation_state"), str):
            raise ValueError("Missing saved skill meaning/state")
        for name in ("resume_evidence_strength", "skill_gap", "priority"):
            value = row.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise ValueError("Invalid saved score")
            if name != "priority" and value is not None and value > 1:
                raise ValueError("Saved score out of range")
        if row.get("resume_evidence_strength") is None and (row.get("skill_gap") is not None or row.get("priority") is not None):
            raise ValueError("An unscored saved skill cannot have a computed gap/priority")
        selected.append({key: deepcopy(row[key]) for key in _SKILL_FIELDS if key in row})
    for name in ("priority_order", "unscored_skill_ids"):
        values = report.get(name)
        if (not isinstance(values, list) or any(not isinstance(item, str) or item not in identifiers for item in values)
                or len(set(values)) != len(values)):
            raise ValueError("Invalid saved ranking")
    sources = report.get("source_index", {})
    if not isinstance(sources, dict) or any(not isinstance(key, str) or not isinstance(value, dict)
                                            for key, value in sources.items()):
        raise ValueError("Invalid saved evidence index")
    result = {key: deepcopy(report[key]) for key in _TOP_FIELDS if key in report}
    result.update(skills=selected, source_index=deepcopy(sources))
    return _public_data(result)


def _public_data(value):
    # Identity selection stays server-side. Artifacts are data, never tool permissions.
    private = {"user_id", "reviewed_resume", "credentials", "access_token", "refresh_token",
               "database_url", "file_path", "filesystem_path"}
    if isinstance(value, dict):
        return {key: _public_data(item) for key, item in value.items() if key.lower() not in private}
    if isinstance(value, list):
        return [_public_data(item) for item in value]
    return value


class ReadOnlyReportSource:
    def __init__(self, directory: Path | None = None) -> None:
        # Resolving does not create the directory or recover/mutate any run.
        self.directory = (directory or BACKEND_ROOT / "local_results" / "web_skill_gaps").resolve()

    def get_report(self, snapshot: ResumeSnapshot, *, report_id: str | None = None) -> dict:
        """Read a checked page selection, or the newest matching saved run.

        A page-supplied ID selects a candidate only; it grants no data access and
        is never replaced by another report when its checks fail.
        """
        if report_id is not None and (not isinstance(report_id, str) or not _RUN_ID.fullmatch(report_id)):
            raise HTTPException(422, "The saved report identifier is invalid.")
        candidates = []
        stale = False
        invalid = False
        try:
            if not self.directory.exists():
                raise HTTPException(404, "No saved skill-gap report is available for this career direction.")
            if report_id is not None:
                selected = self.directory / report_id
                if not selected.exists():
                    raise HTTPException(404, "The selected saved skill-gap report is unavailable.")
                folders = [selected]
            else:
                folders = sorted(self.directory.iterdir())
            for count, folder in enumerate(folders, start=1):
                if count > 10_000:
                    raise ValueError("Too many saved artifacts")
                if not _RUN_ID.fullmatch(folder.name):
                    continue
                if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != self.directory:
                    invalid = True
                    continue
                try:
                    state = _read_json(folder / "status.json", limit=1_000_000)
                except (OSError, ValueError, TypeError, RecursionError):
                    invalid = True
                    continue
                # Never read a report or resume artifact before checking its account/direction.
                if state.get("user_id") != str(snapshot.user_id) or state.get("job_family") != snapshot.job_family:
                    continue
                _validate_state(state, folder.name)
                if state["resume_id"] != str(snapshot.id) or state["resume_hash"] != snapshot.resume_hash:
                    stale = True
                    continue
                candidates.append((_timestamp(state["created_at"]), folder.name, state, folder))
            if not candidates:
                if invalid:
                    raise ValueError("Saved metadata is unavailable")
                if stale:
                    raise HTTPException(409, "The saved skill-gap report is for a different resume version. No matching report was read.")
                raise HTTPException(404, "No saved skill-gap report is available for this career direction.")
            _, _, state, folder = max(candidates, key=lambda item: (item[0], item[1]))
            if state["status"] != "completed":
                messages = {"queued": "The latest matching skill-gap report is still queued.",
                            "running": "The latest matching skill-gap report is not complete yet.",
                            "failed": "The latest matching skill-gap analysis failed. No completed current report was read."}
                raise HTTPException(409, messages[state["status"]])
            reviewed = _read_json(folder / "reviewed_resume.json", limit=4_000_000)
            if (reviewed.get("confirmed") is not True or reviewed.get("resume_source") != "resumes.confirmed_data"
                    or reviewed.get("user_id") != str(snapshot.user_id) or reviewed.get("resume_id") != str(snapshot.id)
                    or reviewed.get("job_family") != snapshot.job_family or reviewed.get("resume_hash") != snapshot.resume_hash
                    or canonical_hash(reviewed.get("reviewed_resume")) != snapshot.resume_hash):
                raise ValueError("Saved report input does not match this resume")
            report = _read_json(folder / "skill_gaps.json", limit=4_000_000)
            if (report.get("user_id") != str(snapshot.user_id) or report.get("resume_id") != str(snapshot.id)
                    or report.get("job_family") != snapshot.job_family or report.get("database_used") is not True):
                raise ValueError("Saved report ownership does not match")
            result = {"run_id": state["id"], "resume_id": str(snapshot.id), "job_family": snapshot.job_family,
                      "created_at": state["created_at"], "completed_at": state["completed_at"],
                      "calculation_fingerprint": state["calculation_fingerprint"],
                      "freshness": "Saved report for the current resume; current algorithm and cloud versions were not revalidated.",
                      "report": _project_report(report)}
            if len(json.dumps(result, ensure_ascii=False, allow_nan=False)) > MAX_REPORT_CHARACTERS:
                raise ValueError("Saved report is too large for this conversation")
            return result
        except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
            raise HTTPException(503, "The saved skill-gap report could not be read. Please try again.") from None
