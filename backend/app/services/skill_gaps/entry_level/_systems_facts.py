"""Apply fact-dependent scoring and preserve valid unused proofs as warnings."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal
import re

from jsonschema import Draft202012Validator

from . import _systems_gates as previous

base = previous.base
sha = previous.sha
TASK = previous.TASK
CONTRACT_VERSION = "entry-level-systems-fact-refinement.v1"
POLICY_VERSION = "independent-execution-blocked-children-unused-proofs.v1"
VALIDATION_VERSION = "systems-refined-fact-structural-checks.v1"
UNUSED_PROOF_POLICY_VERSION = "valid-unused-proof-warning.v1"
llm_status = previous.llm_status
rag_status = previous.rag_status


def build_payload(original_group_payload, packet, variant="rules"):
    payload = previous.build_payload(original_group_payload, packet, variant)
    payload["contract_version"] = CONTRACT_VERSION
    payload["systems_fact_policy_version"] = POLICY_VERSION
    payload["input_sha256"] = sha({k: v for k, v in payload.items() if k != "input_sha256"})
    return payload


def _previous_payload(payload):
    value = deepcopy(payload)
    value["contract_version"] = previous.CONTRACT_VERSION
    value["systems_fact_policy_version"] = previous.POLICY_VERSION
    value["input_sha256"] = sha({k: v for k, v in value.items() if k != "input_sha256"})
    return value


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unknown refined fact input contract")
    if payload.get("systems_fact_policy_version") != POLICY_VERSION:
        raise ValueError("Unknown refined fact policy")
    if payload.get("input_sha256") != sha({k: v for k, v in payload.items() if k != "input_sha256"}):
        raise ValueError("Frozen input fingerprint mismatch")
    return previous.validate_payload(_previous_payload(payload))


def build_format(group, family):
    result = deepcopy(previous.build_format(group, family))
    result["name"] = "entry_systems_fact_refinement_ai_engineer_v1"
    rag = result["schema"]["properties"]["result"]["properties"]["rag"]
    rag["properties"]["criteria"]["minItems"] = 0
    properties = result["schema"]["properties"]
    result["schema"]["properties"] = {key: properties[key] for key in ("task", "result", "proofs")}
    result["schema"]["required"] = ["task", "result", "proofs"]
    # Conditional empty-or-two enforcement is deterministic in Python. The
    # provider schema intentionally uses only the supported strict subset.
    return result


def _refresh_scores(assessment):
    """Reapply the frozen arithmetic after an explicit validation policy change."""
    for row in assessment["skills"]:
        errors = row["errors"]
        weighted = Decimal(0)
        if not errors:
            for audit in row["criterion_audits"]:
                point = base.POINTS.get(audit["status"])
                if point is None:
                    errors.append("unresolved_criterion_after_policy_mapping")
                    break
                weighted += Decimal(str(audit["weight"])) * point
        capped = not errors and row["criterion_audits"][0]["status"] != "supported" and weighted > Decimal("0.6")
        if capped:
            weighted = Decimal("0.6")
        score = None if errors else weighted
        gap = None if score is None else Decimal(1) - score
        row.update(entry_level_score=None if score is None else float(score),
                   entry_level_gap=None if gap is None else float(gap), entry_level_grade=base.grade(gap),
                   calculation_state="needs_confirmation" if errors else "scored", critical_cap_applied=capped)
    assessment["unscored_skill_ids"] = [row["skill_id"] for row in assessment["skills"] if row["entry_level_score"] is None]


def _apply_unused_proof_policy(assessment, output):
    validation = assessment["validation"]
    unused = validation.get("raw_unused_proof_ids", [])
    raw = output if isinstance(output, dict) else {}
    proofs = raw.get("proofs", []) if isinstance(raw.get("proofs", []), list) else []
    ids = Counter(p["proof_id"] for p in proofs if isinstance(p, dict) and isinstance(p.get("proof_id"), str))
    spans = Counter((p["unit_id"], p["quote"]) for p in proofs if isinstance(p, dict)
                    and isinstance(p.get("unit_id"), str) and isinstance(p.get("quote"), str))
    audits = validation.get("raw_proof_pool", [])
    valid, invalid = [], []
    for pid in unused:
        matching = [p for p in audits if p.get("proof_id") == pid]
        eligible = len(matching) == 1 and ids[pid] == 1 and re.fullmatch(r"p[1-9][0-9]*", pid)
        if eligible:
            proof = matching[0]
            uid, quote = proof.get("unit_id"), proof.get("quote")
            original = next(p for p in proofs if isinstance(p, dict) and p.get("proof_id") == pid)
            eligible = (not proof["errors"] and isinstance(uid, str) and isinstance(quote, str)
                        and spans[(uid, quote)] == 1 and set(original) == {"proof_id", "unit_id", "quote"})
        (valid if eligible else invalid).append(pid)
    validation["global_errors"] = [e for e in validation["global_errors"] if e != "unused_proofs"]
    if invalid:
        validation["global_errors"].append("invalid_unused_proofs")
    validation["warnings"] = [{"code": "valid_unused_proofs", "proof_ids": valid}] if valid else []
    validation["unused_proof_policy"] = UNUSED_PROOF_POLICY_VERSION
    validation["valid_unused_proof_ids"] = valid
    validation["invalid_unused_proof_ids"] = invalid
    validation["unused_proofs_grant_credit"] = False
    for row in assessment["skills"]:
        row["errors"] = [e for e in row["errors"] if e != "unused_proofs"]
        if invalid and "invalid_unused_proofs" not in row["errors"]:
            row["errors"].append("invalid_unused_proofs")
    _refresh_scores(assessment)
    return assessment


def assess_output(output, payload):
    family, group, _ = validate_payload(payload)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(build_format(group, family)["schema"]).iter_errors(output)]
    raw = output if isinstance(output, dict) else {}
    body = raw.get("result", {}) if isinstance(raw.get("result", {}), dict) else {}
    rag = body.get("rag", {}) if isinstance(body.get("rag", {}), dict) else {}
    facts = rag.get("core_facts", {}) if isinstance(rag.get("core_facts", {}), dict) else {}
    criteria = rag.get("criteria")
    blocked = rag_status(facts) == "uncertain"
    expected_ids = [] if blocked else ["c2", "c3"]
    observed_ids = [c.get("criterion_id") if isinstance(c, dict) else None for c in criteria] if isinstance(criteria, list) else None
    conditional_errors = [] if observed_ids == expected_ids else ["rag_conditional_child_shape_invalid"]
    projected = deepcopy(output)
    if blocked and criteria == [] and isinstance(projected, dict):
        projected["result"]["rag"]["criteria"] = [
            {"criterion_id": cid, "status": "not_evidenced", "basis": "none", "proof_ids": []}
            for cid in ("c2", "c3")
        ]
    assessment = previous.assess_output(projected, _previous_payload(payload))
    # Only the old forced ambiguous+unclear coupling is removed. Its exact
    # quotes, evidence permissions and non-performed empty fields still apply.
    llm = assessment["fact_audits"]["llm"]
    llm["errors"] = [e for e in llm["errors"] if e != "ambiguous_check_requires_unclear_link"]
    llm_facts = llm["raw_facts"]
    if llm_facts.get("event") == "ambiguous" and llm_facts.get("workload_link") == "not_applicable":
        llm["errors"].append("ambiguous_check_requires_attribution_state")
    for row in assessment["skills"]:
        if row["skill_id"] == "llm":
            row["errors"] = [e for e in row["errors"] if e != "fact:ambiguous_check_requires_unclear_link"]
            if "ambiguous_check_requires_attribution_state" in llm["errors"]:
                row["errors"].append("fact:ambiguous_check_requires_attribution_state")
        if row["skill_id"] == "rag":
            row["errors"].extend(conditional_errors)
        if schema_errors and "response_schema_invalid" not in row["errors"]:
            row["errors"].append("response_schema_invalid")
    assessment["raw_criterion_judgments"]["rag"] = deepcopy(criteria)
    if blocked and criteria == []:
        assessment["raw_blocked_child_audits"] = []
    assessment.update(contract_version=CONTRACT_VERSION, validation_version=VALIDATION_VERSION,
                      input_sha256=payload["input_sha256"], raw_response_sha256=sha(output))
    validation = assessment["validation"]
    validation["schema_errors"] = schema_errors
    if schema_errors and "response_schema_invalid" not in validation["global_errors"]:
        validation["global_errors"].append("response_schema_invalid")
    validation["conditional_output_errors"] = conditional_errors
    validation["blocked_children_emitted_by_model"] = blocked and criteria != []
    validation["internal_unassessed_child_projection"] = blocked and criteria == []
    validation["raw_output_modified"] = False
    return _apply_unused_proof_policy(assessment, output)
