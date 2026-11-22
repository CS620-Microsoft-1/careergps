"""Apply bounded partial credit to independently evidenced Systems components."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from jsonschema import Draft202012Validator

from app.services.skill_gaps.schema import obj
from . import _systems_vector as previous
from . import _systems_facts as proof_policy
from ._lifecycle import _pool

TARGETS = ("vector_retrieval", "rag", "ai_agents", "ai_infrastructure")
CONTRACT_VERSION = "entry-level-affirmative-partial-core.v1"
POLICY_VERSION = "bounded-personal-core-components.v1"
TASK = previous.TASK
sha = previous.sha
build_payload = previous.build_payload
validate_payload = previous.validate_payload

PARTIAL_PREDICATES = {
    "vector_retrieval": (
        "The applicant completed a concrete design deliverable for one retrieval task, "
        "specifying its input, retrieval mechanism and expected returned output. The selected "
        "work is explicitly limited to design and the retrieval operation was not executed."
    ),
    "rag": (
        "The applicant implemented or ran external-evidence retrieval for an identified task "
        "and assembled or handed off its context. The selected personal task explicitly ends "
        "at evidence/context handoff before model generation."
    ),
    "ai_agents": (
        "The applicant implemented a tool adapter or result handoff in an identified workflow "
        "that involves a model. Tool/action control is explicitly entirely fixed code or human "
        "control, without model-mediated tool/action control in the selected personal task."
    ),
    "ai_infrastructure": (
        "The applicant personally used explicit GPU or worker resource metrics to diagnose an "
        "identified AI workload, naming the resource metric. The selected role is explicitly "
        "limited to diagnosis, without claiming configuration or operation of infrastructure."
    ),
}


def build_format(group, family):
    result = deepcopy(previous.build_format(group, family))
    result["name"] = "entry_systems_affirmative_partial_core_v1"
    proof_list = {"anyOf": [{"type": "null"}, {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2}]}
    schema = result["schema"]
    fields = schema["properties"]
    schema["properties"] = {"task": fields["task"], "result": fields["result"],
                            "partial_core": obj({sid: deepcopy(proof_list) for sid in TARGETS}), "proofs": fields["proofs"]}
    schema["required"] = ["task", "result", "partial_core", "proofs"]
    return result


def _partial_audit(sid, assertion, payload, pool):
    errors, proofs = [], []
    if assertion is None:
        return {"assertion": None, "proofs": [], "errors": [], "predicate": PARTIAL_PREDICATES[sid],
                "semantic_truth_verified": False, "outcome": "not_claimed"}
    if not isinstance(assertion, list) or not 1 <= len(assertion) <= 2 or any(not isinstance(pid, str) for pid in assertion):
        errors.append("invalid_partial_proof_references")
        refs = assertion if isinstance(assertion, list) else []
    else:
        refs = assertion
        if len(set(refs)) != len(refs):
            errors.append("duplicate_partial_proof_reference")
    allowed = payload["fixed_evidence_packets"]["skills"][sid]["criterion_unit_ids"]["c1"]
    for pid in refs:
        proof = pool.get(pid) if isinstance(pid, str) else None
        if proof is None:
            errors.append("unknown_partial_proof_id")
            continue
        errors.extend(proof["errors"])
        if proof["unit_id"] not in allowed:
            errors.append("partial_proof_outside_fixed_c1_candidates")
        if proof["kind"] != "claim":
            errors.append("partial_requires_claim_source")
        proofs.append(deepcopy(proof))
    return {"assertion": deepcopy(assertion), "proofs": proofs, "errors": list(dict.fromkeys(errors)),
            "predicate": PARTIAL_PREDICATES[sid], "semantic_truth_verified": False, "outcome": "unassessed"}


def _bounded_fact_guard(sid, body):
    record = body.get(sid, {}) if isinstance(body.get(sid, {}), dict) else {}
    facts = record.get("core_facts", {}) if isinstance(record.get("core_facts", {}), dict) else {}
    if sid == "vector_retrieval":
        return (facts.get("claim_kind") == "design" and facts.get("execution") == "explicitly_not_performed"
                and isinstance(facts.get("method"), str) and facts["method"] in previous.ELIGIBLE_METHODS
                and facts.get("ownership") == "personal" and facts.get("workload_link") == "same"
                and record.get("children") is None)
    if sid == "rag":
        return (facts.get("personal_retrieval") == "performed" and facts.get("model_generation") == "explicitly_absent"
                and facts.get("retrieval_use") == "unspecified_output" and facts.get("workload_link") == "not_applicable"
                and record.get("children") is None)
    criteria = record.get("criteria", [])
    return (isinstance(criteria, list) and len(criteria) == 3
            and all(isinstance(c, dict) and c.get("status") == "not_evidenced"
                    and c.get("basis") == "none" and c.get("proof_ids") == [] for c in criteria))


def assess_output(output, payload):
    """Add a bounded component only after unchanged v9 validation succeeds."""
    family, group, _ = validate_payload(payload)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(build_format(group, family)["schema"]).iter_errors(output)]
    raw = output if isinstance(output, dict) else {}
    body = raw.get("result", {}) if isinstance(raw.get("result", {}), dict) else {}
    assertions = raw.get("partial_core", {}) if isinstance(raw.get("partial_core", {}), dict) else {}
    raw_proofs, pool, pool_audits, global_errors = _pool(output, payload)
    audits = {sid: _partial_audit(sid, assertions.get(sid), payload, pool) for sid in TARGETS}
    partial_refs = {pid for value in assertions.values() if isinstance(value, list) for pid in value if isinstance(pid, str)}
    prior_refs = previous._used_proofs(body)
    projected = deepcopy(raw)
    projected.pop("partial_core", None)
    partial_only = partial_refs - prior_refs
    # Independently validated component citations are not old-result orphans.
    # True unused proofs stay in the projection and retain the v9 warning rule.
    projected["proofs"] = [p for p in raw_proofs if not (isinstance(p, dict) and isinstance(p.get("proof_id"), str) and p["proof_id"] in partial_only)]
    assessment = previous.assess_output(projected, payload)
    if schema_errors:
        global_errors.append("response_schema_invalid")
    rows = {row["skill_id"]: row for row in assessment["skills"]}
    for sid, row in rows.items():
        errors = list(global_errors)
        if sid in audits:
            errors.extend("partial_core:" + error for error in audits[sid]["errors"])
        row["errors"] = list(dict.fromkeys(row["errors"] + errors))
    validation = assessment["validation"]
    validation["schema_errors"] = schema_errors
    validation["global_errors"] = list(dict.fromkeys(validation["global_errors"] + global_errors))
    validation.update(raw_proof_pool=pool_audits, raw_unused_proof_ids=sorted(set(pool) - prior_refs - partial_refs),
                      raw_proof_count=len(raw_proofs), raw_output_modified=False, semantic_validation_performed=False)
    proof_policy._apply_unused_proof_policy(assessment, output)
    applied = []
    for sid, audit in audits.items():
        row = rows[sid]
        row["partial_core_applied"] = False
        full_core = row["criterion_audits"][0]["status"]
        audit["full_core_status"] = full_core
        if audit["assertion"] is None:
            audit["outcome"] = "not_claimed"
        elif row["errors"]:
            audit["outcome"] = "pending_preserved"
        elif full_core == "supported":
            audit["outcome"] = "full_core_priority"
            audit["semantic_conflict_review_required"] = True
            audit["partial_assertion_applied"] = False
        elif full_core != "not_evidenced":
            audit["outcome"] = "pending_preserved"
        elif not _bounded_fact_guard(sid, body):
            audit["outcome"] = "inconsistent_bounded_component"
            audit["errors"].append("partial_assertion_conflicts_with_existing_facts")
            row["errors"].append("partial_core:partial_assertion_conflicts_with_existing_facts")
            row.update(entry_level_score=None, entry_level_gap=None, entry_level_grade=proof_policy.base.grade(None),
                       calculation_state="needs_confirmation", critical_cap_applied=False)
        else:
            audit["outcome"] = "applied"
            c1 = row["criterion_audits"][0]
            c1.update(status="partial", basis="practice", points=0.5,
                      proofs=[{key: deepcopy(value) for key, value in p.items() if key != "errors"} for p in audit["proofs"]],
                      partial_core_predicate=POLICY_VERSION, dependency_derived=True)
            for child in row["criterion_audits"][1:]:
                child.update(status="blocked_by_partial_core", basis="unassessed", points=0.0,
                             proofs=[], errors=[], dependency_derived=True)
            row.update(entry_level_score=0.25, entry_level_gap=0.75, entry_level_grade=proof_policy.base.grade(Decimal("0.75")),
                       calculation_state="scored", critical_cap_applied=False, partial_core_applied=True)
            applied.append(sid)
    assessment.update(contract_version=CONTRACT_VERSION, partial_core_policy_version=POLICY_VERSION,
                      input_sha256=payload["input_sha256"], raw_response_sha256=sha(output),
                      partial_core_audits=audits, partial_core_applied=applied,
                      unscored_skill_ids=[row["skill_id"] for row in assessment["skills"] if row["entry_level_score"] is None])
    return assessment
