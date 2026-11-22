"""Validate vector retrieval facts and their dependent criteria."""
from __future__ import annotations

from copy import deepcopy

from jsonschema import Draft202012Validator

from app.services.skill_gaps.schema import choice, obj
from . import _systems_checks as previous
from . import _systems_facts as proof_policy
from ._lifecycle import _pool

TASK = previous.TASK
sha = previous.sha
SKILL = "vector_retrieval"
CONTRACT_VERSION = "entry-level-vector-core-facts.v1"
POLICY_VERSION = "vector-operation-execution-facts.v1"
VALIDATION_VERSION = "vector-core-fact-validation.v1"
ELIGIBLE_METHODS = {"embeddings", "similarity_search", "vector_indexing", "vector_storage", "multiple_eligible"}


def build_payload(original_group_payload, packet, variant="rules"):
    result = previous.build_payload(original_group_payload, packet, variant)
    result["contract_version"] = CONTRACT_VERSION
    result["vector_core_policy_version"] = POLICY_VERSION
    result["input_sha256"] = sha({k: v for k, v in result.items() if k != "input_sha256"})
    return result


def _previous_payload(payload):
    result = deepcopy(payload)
    result["contract_version"] = previous.CONTRACT_VERSION
    result.pop("vector_core_policy_version", None)
    result["input_sha256"] = sha({k: v for k, v in result.items() if k != "input_sha256"})
    return result


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unknown Vector Retrieval fact contract")
    if payload.get("vector_core_policy_version") != POLICY_VERSION:
        raise ValueError("Unknown Vector Retrieval fact policy")
    if payload.get("input_sha256") != sha({k: v for k, v in payload.items() if k != "input_sha256"}):
        raise ValueError("Frozen input fingerprint mismatch")
    return previous.validate_payload(_previous_payload(payload))


def build_format(group, family):
    result = deepcopy(previous.build_format(group, family))
    result["name"] = "entry_systems_vector_core_facts_ai_engineer_v1"
    schema = result["schema"]
    facts = obj({
        "claim_kind": choice("operation", "design", "evaluation", "tool_list", "absent", "unclear"),
        "execution": choice("performed", "explicitly_not_performed", "not_stated", "unclear", "not_applicable"),
        "method": choice("embeddings", "similarity_search", "vector_indexing", "vector_storage", "multiple_eligible", "unrelated", "not_stated", "unclear", "not_applicable"),
        "ownership": choice("personal", "others_only", "unclear", "not_applicable"),
        "workload_link": choice("same", "other", "unclear", "not_applicable"),
        "proof_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
    })
    children = deepcopy(schema["properties"]["result"]["properties"]["rag"]["properties"]["children"])
    schema["properties"]["result"]["properties"][SKILL] = obj({"core_facts": facts, "children": children})
    return result


def _string(value):
    return value if isinstance(value, str) else None


def vector_status(facts):
    kind, execution, method, owner, link = (_string(facts.get(k)) for k in
        ("claim_kind", "execution", "method", "ownership", "workload_link"))
    if kind in {"tool_list", "absent"} or execution == "explicitly_not_performed" or method == "unrelated" or owner == "others_only" or link == "other":
        return "not_evidenced"
    if execution == "performed" and method in ELIGIBLE_METHODS and owner == "personal" and link == "same":
        return "supported"
    return "uncertain"


core_status = vector_status


def _refs(item):
    refs = item.get("proof_ids", []) if isinstance(item, dict) else []
    return refs if isinstance(refs, list) else []


def _fact_audit(facts, payload, pool):
    refs, errors, proofs = _refs(facts), [], []
    if len(refs) > 2 or any(not isinstance(pid, str) for pid in refs):
        errors.append("invalid_fact_proof_references")
    elif len(set(refs)) != len(refs):
        errors.append("duplicate_fact_proof_reference")
    allowed = payload["fixed_evidence_packets"]["skills"][SKILL]["criterion_unit_ids"]["c1"]
    for pid in refs:
        proof = pool.get(pid) if isinstance(pid, str) else None
        if proof is None:
            errors.append("unknown_fact_proof_id")
            continue
        errors.extend(proof["errors"])
        if proof["unit_id"] not in allowed:
            errors.append("fact_proof_outside_fixed_criterion_candidates")
        if facts.get("execution") == "performed" and proof["kind"] != "claim":
            errors.append("performed_fact_requires_claim_source")
        proofs.append(deepcopy(proof))
    simple_absence = facts.get("claim_kind") == "absent" and all(
        facts.get(key) == "not_applicable" for key in ("execution", "method", "ownership", "workload_link"))
    if not refs and not simple_absence:
        errors.append("claimed_vector_facts_without_proof")
    return {"raw_facts": deepcopy(facts), "mapped_status": vector_status(facts),
            "proofs": proofs, "errors": list(dict.fromkeys(errors)), "semantic_truth_verified": False}


def _used_proofs(body):
    used = set()
    for record in body.values():
        if not isinstance(record, dict):
            continue
        items = [record.get("check_facts"), record.get("core_facts")]
        criteria = record.get("criteria", [])
        if isinstance(criteria, list):
            items.extend(criteria)
        children = record.get("children")
        if isinstance(children, dict):
            items.extend(children.values())
        for item in items:
            used.update(pid for pid in _refs(item) if isinstance(pid, str))
    return used


def assess_output(output, payload):
    family, group, _ = validate_payload(payload)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(build_format(group, family)["schema"]).iter_errors(output)]
    raw = output if isinstance(output, dict) else {}
    body = raw.get("result", {}) if isinstance(raw.get("result", {}), dict) else {}
    record = body.get(SKILL, {}) if isinstance(body.get(SKILL, {}), dict) else {}
    facts = record.get("core_facts", {}) if isinstance(record.get("core_facts", {}), dict) else {}
    raw_proofs, pool, pool_audits, global_errors = _pool(output, payload)
    fact_audit = _fact_audit(facts, payload, pool)
    status = fact_audit["mapped_status"]
    children = record.get("children")
    shape_ok = ((isinstance(children, dict) and set(children) == {"c2", "c3"}) if status == "supported"
                else "children" in record and children is None)
    conditional = [] if shape_ok else ["vector_conditional_child_shape_invalid"]
    if isinstance(children, dict):
        child_rows = [{**deepcopy(children[cid]), "criterion_id": cid} if isinstance(children.get(cid), dict) else children.get(cid)
                      for cid in ("c2", "c3")]
    else:
        child_rows = [{"criterion_id": cid, "status": "not_evidenced", "basis": "none", "proof_ids": []} for cid in ("c2", "c3")]
    mapped = {"criterion_id": "c1", "status": status,
              "basis": "practice" if status == "supported" else "unclear" if status == "uncertain" else "none",
              "proof_ids": deepcopy(_refs(facts)) if status != "not_evidenced" else []}
    projected = deepcopy(raw)
    projected["result"] = deepcopy(body)
    projected["result"][SKILL] = {"criteria": [mapped] + child_rows}
    projected_used = _used_proofs(projected["result"])
    # Negative fact context is validated above but is not a scored criterion
    # citation. Genuine orphan proofs remain for the unchanged shared policy.
    fact_only_negative = set(pid for pid in _refs(facts) if isinstance(pid, str)) - projected_used if status == "not_evidenced" else set()
    projected["proofs"] = [p for p in raw_proofs if not (isinstance(p, dict) and isinstance(p.get("proof_id"), str) and p["proof_id"] in fact_only_negative)]
    assessment = previous.assess_output(projected, _previous_payload(payload))
    if schema_errors:
        global_errors.append("response_schema_invalid")
    vector_row = next(row for row in assessment["skills"] if row["skill_id"] == SKILL)
    raw_child_audits = deepcopy(vector_row["criterion_audits"][1:]) if isinstance(children, dict) else []
    if status == "uncertain" and children is None:
        for audit in vector_row["criterion_audits"][1:]:
            audit.update(status="blocked_by_unresolved_core", basis="unassessed", points=None,
                         reported_status=None, reported_basis=None, proofs=[], errors=["blocked_by_unresolved_core"])
        vector_row["errors"].append("children_blocked_by_unresolved_core")
    vector_row["errors"].extend("fact:" + e for e in fact_audit["errors"])
    vector_row["errors"].extend(conditional)
    for row in assessment["skills"]:
        row["errors"] = list(dict.fromkeys(row["errors"] + global_errors))
    assessment["fact_audits"][SKILL] = fact_audit
    assessment["raw_criterion_judgments"][SKILL] = deepcopy(children)
    validation = assessment["validation"]
    validation["schema_errors"] = schema_errors
    validation["global_errors"] = list(dict.fromkeys(validation["global_errors"] + global_errors))
    validation["conditional_output_errors"] = list(dict.fromkeys(validation.get("conditional_output_errors", []) + conditional))
    validation.update(raw_proof_pool=pool_audits, raw_unused_proof_ids=sorted(set(pool) - _used_proofs(body)),
                      raw_proof_count=len(raw_proofs), vector_child_state="assessed" if status == "supported" else "blocked_by_unresolved_core" if status == "uncertain" else "skipped_due_to_absent_core",
                      vector_children_dependency_derived=status != "supported" and children is None,
                      raw_output_modified=False, semantic_validation_performed=False)
    assessment.update(contract_version=CONTRACT_VERSION, validation_version=VALIDATION_VERSION,
                      input_sha256=payload["input_sha256"], raw_response_sha256=sha(output),
                      raw_vector_children=deepcopy(children), raw_vector_child_audits=raw_child_audits)
    return proof_policy._apply_unused_proof_policy(assessment, output)
