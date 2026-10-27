"""Expose unselected proof candidates without reusing them or changing scores.

This audit runs after mechanical reference validation. A proof selected for one
core may be worth reviewing for another core that selected the same operation,
but neither the shared operation nor a real quote establishes semantic relevance.
"""
from copy import deepcopy


SCOPE = "candidate_references_only_no_semantic_reuse_or_score_changes"


def _proof(value):
    """Copy a passed record's proof shape; do not revalidate its source/meaning."""
    if not isinstance(value, dict) or not all(key in value for key in ("unit_id", "quote")):
        return None
    return {"unit_id": deepcopy(value["unit_id"]), "quote": deepcopy(value["quote"])}


def audit_coverage(agent_output, checks, sources):
    """List candidate method/check references only for matching operation IDs.

Null fields mean the model did not select a feature, not that it overlooked an
existing fact. Only mechanically passed practice records participate. ``sources``
is accepted for pipeline consistency; the prior checker owns source integrity.
No source parsing, category inference, automatic filling or score gate occurs.
    """
    result = {"scope": SCOPE, "method_null_skill_ids": [],
              "validation_null_skill_ids": [], "candidate_references": {}}
    body = agent_output.get("result") if isinstance(agent_output, dict) else None
    statuses = checks.get("skills") if isinstance(checks, dict) else None
    if not isinstance(body, dict) or not isinstance(statuses, dict):
        return result

    records = {}
    for skill_id in sorted(body):
        record, status = body[skill_id], statuses.get(skill_id)
        if (not isinstance(record, dict) or record.get("kind") not in ("practice", "limited_practice")
                or not isinstance(status, dict) or status.get("status") != "passed"
                or not isinstance(record.get("operation_id"), str) or not record["operation_id"]):
            continue
        records[skill_id] = record
        if "method" in record and record["method"] is None:
            result["method_null_skill_ids"].append(skill_id)
        if "validation" in record and record["validation"] is None:
            result["validation_null_skill_ids"].append(skill_id)

    for skill_id, record in records.items():
        missing_method = skill_id in result["method_null_skill_ids"]
        missing_check = skill_id in result["validation_null_skill_ids"]
        if not (missing_method or missing_check):
            continue
        candidates, seen = {"method": [], "check": []}, {"method": set(), "check": set()}
        for provider_id, provider in records.items():
            if provider_id == skill_id or provider["operation_id"] != record["operation_id"]:
                continue
            method, validation = provider.get("method"), provider.get("validation")
            supplied = {
                "method": _proof(method.get("proof")) if isinstance(method, dict) else None,
                "check": _proof(validation.get("check")) if isinstance(validation, dict) else None,
            }
            for facet, needed in (("method", missing_method), ("check", missing_check)):
                proof = supplied[facet]
                if not needed or proof is None:
                    continue
                # Passed v12 proofs have string fields. The guard merely prevents
                # malformed caller data from crashing this non-authoritative audit.
                if not all(isinstance(proof[key], str) for key in ("unit_id", "quote")):
                    continue
                identity = (proof["unit_id"], proof["quote"])
                if identity not in seen[facet]:
                    seen[facet].add(identity)
                    candidates[facet].append({"from_skill": provider_id, "proof": proof})
        if candidates["method"] or candidates["check"]:
            result["candidate_references"][skill_id] = candidates
    return result
