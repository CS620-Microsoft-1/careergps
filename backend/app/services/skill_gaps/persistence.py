"""Turn a Skill Gap run into database rows. Pure functions: no database, files or model calls.

The rows follow docs/contracts/skill-gap-run-storage.schema.json v3 and the tables in
app/models/skill_gap.py: one skill_gap_runs row, one skill_gap_run_branches row per skill group and one
skill_gap_results row per core skill. The report itself is stored unchanged; these functions only copy
what other agents query into columns. Values come from students' résumés: never log them.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from typing import Any
from uuid import UUID

from .match import summarize_match
from .schema import SCHEMA_NAME
from .scoring import POLICY_VERSION
from .skill_groups import GROUPS

STORAGE_SCHEMA_VERSION = "careergps.skill_gap_run_storage.v3"

# Proof-span field suffixes (validation.py) → evidence roles (contract EvidenceItem.role).
_SPAN_ROLES = {
    "capability/quote": "capability",
    "method/proof/quote": "method",
    "validation/check/quote": "check",
    "validation/finding/quote": "finding",
    "validation/reference/quote": "reference",
}
_PRACTICE = {"practice", "limited_practice"}


def canonical_sha256(value: object) -> str:
    """The same canonical JSON hash runs.py uses for résumé hashes and fingerprints."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_uuid(identifier: str | UUID | None) -> UUID | None:
    """Local run ids are uuid4().hex (32 hex characters); the database stores the same value as a UUID."""
    return None if identifier is None else UUID(str(identifier))


def _unit(source_index: dict, unit_id: str) -> dict:
    unit = source_index.get(unit_id)
    if not isinstance(unit, dict) or not isinstance(unit.get("text"), str):
        raise ValueError("A cited résumé unit is missing from the report's source index")
    return unit


def _item(role: str, unit: dict, start: int, end: int) -> dict:
    quote = unit["text"][start:end]
    if not quote or not 0 <= start < end <= len(unit["text"]):
        raise ValueError("A proof span does not select text inside its résumé unit")
    return {"role": role, "unit_id": unit["id"], "activity_id": unit.get("activity_id"),
            "source_path": unit.get("path"), "quote": quote, "start": start, "end": end}


def evidence_items(skill_row: dict, source_index: dict) -> list[dict]:
    """The quoted proofs behind one skill, in the order the checks recorded them.

    Practice evidence uses the checked proof spans (exact positions in the original unit). Knowledge and
    uncertain evidence cite a whole unit. Absent evidence, and an uncertain record without a unit, has none.
    """
    assessment = skill_row["agent_assessment"]
    kind = assessment.get("kind")
    if kind in _PRACTICE:
        items = []
        for span in skill_row["local_reference_check"].get("proof_spans", []):
            # "/result/<skill_id>/capability/quote" → "capability/quote"
            suffix = span["field"].split("/", 3)[3] if span["field"].count("/") >= 3 else ""
            if suffix not in _SPAN_ROLES:
                raise ValueError(f"Unknown proof span field for {skill_row['skill_id']}")
            items.append(_item(_SPAN_ROLES[suffix], _unit(source_index, span["unit_id"]), span["start"], span["end"]))
        return items
    if kind in ("knowledge", "uncertain") and assessment.get("evidence_id"):
        unit = _unit(source_index, assessment["evidence_id"])
        return [_item(kind, unit, 0, len(unit["text"]))]
    return []


def result_rows(report: dict, extraction_audit: dict | None, *, run_id: UUID,
                user_id: UUID, job_family: str) -> list[dict]:
    """One skill_gap_results row per report skill, in catalog order, with its priority rank and evidence."""
    if report.get("job_family") != job_family:
        raise ValueError("The report belongs to a different job family")
    skills = report["skills"]
    rank = {skill_id: index + 1 for index, skill_id in enumerate(report["priority_order"])}
    audit = (extraction_audit or {}).get("skills", {})
    rows = []
    for position, row in enumerate(skills):
        skill_id = row["skill_id"]
        demand = row["demand"]
        merge = audit.get(skill_id)
        rows.append({
            "run_id": run_id, "skill_id": skill_id, "user_id": user_id, "job_family": job_family,
            "position": position, "skill_name": row["skill_name"],
            "module_id": row["module_id"], "module_name": row["module_name"],
            "branch": merge.get("selected_branch") if merge else None,
            "evidence_kind": row["agent_assessment"]["kind"],
            "calculation_state": row["calculation_state"],
            "evidence_strength": row["resume_evidence_strength"], "skill_gap": row["skill_gap"],
            "grade": row["skill_gap_grade"],
            "demand_required_count": demand["required_job_count"],
            "demand_preferred_only_count": demand["preferred_only_job_count"],
            "demand_unspecified_count": demand["unspecified_job_count"],
            "demand_n": demand["N"], "demand_weight": row["demand_weight"], "priority": row["priority"],
            # Only scored skills are ranked; a skill that needs confirmation has no rank.
            "priority_rank": rank.get(skill_id) if row["calculation_state"] == "scored" else None,
            "agent_assessment": deepcopy(row["agent_assessment"]),
            "original_agent_assessment": deepcopy(row.get("original_agent_assessment")),
            "scoring_breakdown": deepcopy(row["scoring_breakdown"]),
            "reference_check": deepcopy(row["local_reference_check"]),
            "merge_audit": deepcopy(merge),
            "evidence": evidence_items(row, report["source_index"]),
        })
    if len({row["skill_id"] for row in rows}) != len(rows):
        raise ValueError("The report lists a skill twice")
    return rows


def completion_fields(report: dict, extraction_audit: dict | None, merged_output: Any) -> dict:
    """The skill_gap_runs columns written when a run completes."""
    match = summarize_match(report)
    scored = sum(row["calculation_state"] == "scored" for row in report["skills"])
    return {
        "report": deepcopy(report), "raw_agent_output": deepcopy(merged_output),
        "extraction_audit": deepcopy(extraction_audit),
        "match_score": match["score"] if match else None,
        "scored_skill_count": scored, "unscored_skill_count": len(report["skills"]) - scored,
    }


def queued_run_row(state: dict, reviewed_resume: dict, *, demand_snapshot_fingerprint: str,
                   catalog_version: str | None, partition_policy_version: str,
                   selection_policy_version: str) -> dict:
    """The skill_gap_runs row inserted when a run is queued, from the manager's in-memory state."""
    return {
        "id": run_uuid(state["id"]), "user_id": UUID(state["user_id"]), "resume_id": UUID(state["resume_id"]),
        "job_family": state["job_family"], "resume_hash": state["resume_hash"],
        "reviewed_resume_snapshot": deepcopy(reviewed_resume),
        "calculation_fingerprint": state["calculation_fingerprint"],
        "demand_snapshot_fingerprint": demand_snapshot_fingerprint,
        "policy_version": POLICY_VERSION, "response_schema_name": SCHEMA_NAME,
        "catalog_version": catalog_version, "prompt_revision": state.get("prompt_revision"),
        "instructions_sha256": state.get("instructions_sha256"),
        "response_processing_version": state.get("response_processing_version"),
        "status": state["status"], "phase": state["phase"],
        "created_at": datetime.fromisoformat(state["created_at"]),
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "resume_filename": state.get("filename"),
        "confirmed_at": datetime.fromisoformat(state["confirmed_at"]) if state.get("confirmed_at") else None,
        "extraction_strategy": state.get("extraction_strategy", "skill_groups"),
        "partition_policy_version": partition_policy_version,
        "selection_policy_version": selection_policy_version,
        "reuse_from_run_id": run_uuid(state.get("reuse_from_run_id")),
    }


def _usage(raw_response: dict | None) -> dict:
    usage = (raw_response or {}).get("usage") or {}
    details_in = usage.get("input_tokens_details") or {}
    details_out = usage.get("output_tokens_details") or {}
    return {"input_tokens": usage.get("input_tokens"), "cached_tokens": details_in.get("cached_tokens"),
            "output_tokens": usage.get("output_tokens"), "reasoning_tokens": details_out.get("reasoning_tokens")}


def branch_row(run_id: UUID, branch: str, branch_state: dict, *, payload: dict | None = None,
               output: Any = None, raw_response: dict | None = None, definition: dict | None = None,
               timings: dict | None = None, validation: dict | None = None,
               response_processing: dict | None = None) -> dict:
    """One skill_gap_run_branches row.

    Token counts and the model come from the group's own raw Agent response. A reused answer made no
    new request, so it records no tokens even when its source run's response is available.
    """
    if branch not in GROUPS:
        raise ValueError("Choose foundation, lifecycle or systems")
    raw = raw_response if raw_response and not branch_state.get("reused") else None
    reasoning = (raw or {}).get("reasoning") or (definition or {}).get("reasoning") or {}
    return {
        "run_id": run_id, "branch": branch, "status": branch_state["status"],
        "agent_name": branch_state.get("agent_name"), "agent_version": branch_state.get("agent_version"),
        "model": (raw or {}).get("model") or (definition or {}).get("model"),
        "reasoning_effort": reasoning.get("effort") if isinstance(reasoning, dict) else None,
        "input_sha256": canonical_sha256(payload) if payload is not None else None,
        "reused": bool(branch_state.get("reused", False)),
        "source_run_id": run_uuid(branch_state.get("source_run_id")),
        "model_calls": branch_state.get("model_calls", 0),
        "elapsed_seconds": branch_state.get("elapsed_seconds", 0.0),
        "inference_seconds": (timings or {}).get("inference_seconds"),
        **_usage(raw),
        "error_code": branch_state.get("error_code"),
        "raw_output": deepcopy(output),
        "validation": deepcopy(validation), "response_processing": deepcopy(response_processing),
    }
