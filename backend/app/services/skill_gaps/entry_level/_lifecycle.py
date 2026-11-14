"""Validate fine-tuning and model-serving facts before scoring Lifecycle skills."""
from __future__ import annotations

from copy import deepcopy
import re

from jsonschema import Draft202012Validator

from app.services.skill_gaps.schema import choice, obj
from app.services.skill_gaps.sources import build_index
from . import _rubric as base
from . import _systems_facts as proof_policy

TASK = base.TASK
sha = base.sha
TARGETS = ("fine_tuning", "model_deployment")
CONTRACT_VERSION = "entry-level-lifecycle-core-facts.v1"
POLICY_VERSION = "fine-tuning-and-serving-core-facts.v1"
VALIDATION_VERSION = "lifecycle-core-fact-validation.v1"


def _scope(group, family):
    if (group, family) != ("lifecycle", "ai_engineer"):
        raise ValueError("This experiment supports AI Engineer Lifecycle only")
    return base._scope(group, family)


def build_payload(original_group_payload, packet, variant="rules"):
    if variant != "rules":
        raise ValueError("This experiment uses the complete rule cards")
    _scope(original_group_payload["evidence_scope"]["branch"], original_group_payload["job_family"])
    result = base.build_payload(original_group_payload, packet, variant)
    result["contract_version"] = CONTRACT_VERSION
    result["lifecycle_core_policy_version"] = POLICY_VERSION
    result["input_sha256"] = sha({k: v for k, v in result.items() if k != "input_sha256"})
    return result


def _base_payload(payload):
    result = deepcopy(payload)
    result["contract_version"] = base.CONTRACT_VERSION
    result.pop("lifecycle_core_policy_version", None)
    result["input_sha256"] = sha({k: v for k, v in result.items() if k != "input_sha256"})
    return result


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unknown Lifecycle core-fact contract")
    if payload.get("lifecycle_core_policy_version") != POLICY_VERSION or payload.get("variant") != "rules":
        raise ValueError("Unknown Lifecycle core-fact policy")
    if payload.get("input_sha256") != sha({k: v for k, v in payload.items() if k != "input_sha256"}):
        raise ValueError("Frozen input fingerprint mismatch")
    _scope(payload["evidence_scope"]["branch"], payload["job_family"])
    return base.validate_payload(_base_payload(payload))


def build_format(group, family):
    _scope(group, family)
    result = deepcopy(base.build_format(group, family))
    result["name"] = "entry_lifecycle_core_facts_ai_engineer_v1"
    schema = result["schema"]
    child = deepcopy(schema["$defs"]["Criterion"])
    child["properties"].pop("criterion_id")
    child["required"].remove("criterion_id")
    schema["$defs"]["Child"] = child
    common = {
        "execution": choice("performed", "planned", "prepared", "absent", "unclear"),
        "ownership": choice("personal", "others_only", "unclear", "not_applicable"),
        "workload_link": choice("same", "other", "unclear", "not_applicable"),
        "proof_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
    }
    specific = {
        "fine_tuning": {
            "pretrained_origin": choice("explicit", "from_scratch", "not_stated", "unclear", "not_applicable"),
            "parameter_update": choice("weights", "adapters", "weights_and_adapters", "explicitly_none", "not_stated", "unclear", "not_applicable"),
        },
        "model_deployment": {
            "serving_identity": choice("runnable_model_serving", "external_api_only", "not_serving", "not_stated", "unclear", "not_applicable"),
        },
    }
    children = {"anyOf": [{"type": "null"}, obj({"c2": {"$ref": "#/$defs/Child"}, "c3": {"$ref": "#/$defs/Child"}})]}
    for sid in TARGETS:
        schema["properties"]["result"]["properties"][sid] = obj({
            "core_facts": obj({**deepcopy(common), **specific[sid]}), "children": deepcopy(children),
        })
    properties = schema["properties"]
    schema["properties"] = {key: properties[key] for key in ("task", "result", "proofs")}
    schema["required"] = ["task", "result", "proofs"]
    return result


def _string(value):
    return value if isinstance(value, str) else None


def core_status(sid, facts):
    if sid not in TARGETS:
        raise ValueError("Unknown core-fact skill")
    execution, ownership, link = (_string(facts.get(k)) for k in ("execution", "ownership", "workload_link"))
    if execution in {"planned", "prepared", "absent"} or ownership == "others_only" or link == "other":
        return "not_evidenced"
    if sid == "fine_tuning":
        origin, update = (_string(facts.get(k)) for k in ("pretrained_origin", "parameter_update"))
        if origin == "from_scratch" or update == "explicitly_none":
            return "not_evidenced"
        defined = origin == "explicit" and update in {"weights", "adapters", "weights_and_adapters"}
    else:
        identity = _string(facts.get("serving_identity"))
        if identity in {"external_api_only", "not_serving"}:
            return "not_evidenced"
        defined = identity == "runnable_model_serving"
    return "supported" if (execution, ownership, link) == ("performed", "personal", "same") and defined else "uncertain"


def _refs(item):
    value = item.get("proof_ids", []) if isinstance(item, dict) else []
    return value if isinstance(value, list) else []


def apply_shared_proof_policy(assessment, output):
    """Both arms call the same unchanged valid-unused-proof policy function."""
    validation = assessment["validation"]
    if "raw_proof_pool" not in validation:
        validation["raw_proof_pool"] = deepcopy(validation["proof_pool"])
    if "raw_unused_proof_ids" not in validation:
        validation["raw_unused_proof_ids"] = deepcopy(validation["unused_proof_ids"])
    validation["raw_proof_count"] = len(output.get("proofs", [])) if isinstance(output, dict) and isinstance(output.get("proofs", []), list) else 0
    return proof_policy._apply_unused_proof_policy(assessment, output)


def _pool(output, payload):
    raw = output.get("proofs", []) if isinstance(output, dict) else []
    raw = raw if isinstance(raw, list) else []
    index = build_index(payload["resume_sources"])
    pool, audits, global_errors, spans = {}, [], [], set()
    for proof in raw:
        if not isinstance(proof, dict) or not isinstance(proof.get("proof_id"), str):
            continue
        pid, uid, quote = proof["proof_id"], proof.get("unit_id"), proof.get("quote")
        errors = []
        if not re.fullmatch(r"p[1-9][0-9]*", pid):
            global_errors.append("invalid_proof_id")
        if pid in pool:
            global_errors.append("duplicate_proof_id")
        unit = index.get(uid) if isinstance(uid, str) else None
        if unit is None:
            errors.append("unknown_source_unit")
        if not isinstance(quote, str) or not quote.strip() or (unit is not None and quote not in unit["text"]):
            errors.append("quote_not_exact")
        if isinstance(uid, str) and isinstance(quote, str):
            key = (uid, quote)
            if key in spans:
                global_errors.append("duplicate_proof_span")
            spans.add(key)
        item = {**deepcopy(proof), "proof_id": pid, "unit_id": uid, "quote": quote,
                "activity_id": unit["activity_id"] if unit else None,
                "kind": unit["kind"] if unit else None, "errors": errors}
        pool[pid] = item
        audits.append(item)
    return raw, pool, audits, list(dict.fromkeys(global_errors))


def _fact_audit(sid, facts, payload, pool):
    refs, errors, proofs = _refs(facts), [], []
    if len(refs) > 2 or any(not isinstance(pid, str) for pid in refs):
        errors.append("invalid_fact_proof_references")
    elif len(refs) != len(set(refs)):
        errors.append("duplicate_fact_proof_reference")
    candidates = payload["fixed_evidence_packets"]["skills"][sid]["criterion_unit_ids"]["c1"]
    for pid in refs:
        proof = pool.get(pid) if isinstance(pid, str) else None
        if proof is None:
            errors.append("unknown_fact_proof_id")
            continue
        errors.extend(proof["errors"])
        if proof["unit_id"] not in candidates:
            errors.append("fact_proof_outside_fixed_criterion_candidates")
        if facts.get("execution") == "performed" and proof["kind"] != "claim":
            errors.append("performed_fact_requires_claim_source")
        proofs.append(deepcopy(proof))
    absence = facts.get("execution") == "absent" and facts.get("ownership") == "not_applicable" and facts.get("workload_link") == "not_applicable"
    identity_fields = ("pretrained_origin", "parameter_update") if sid == "fine_tuning" else ("serving_identity",)
    absence = absence and all(facts.get(key) == "not_applicable" for key in identity_fields)
    if not refs and not absence:
        errors.append("claimed_core_facts_without_proof")
    return {"raw_facts": deepcopy(facts), "mapped_status": core_status(sid, facts),
            "proofs": proofs, "errors": list(dict.fromkeys(errors)), "semantic_truth_verified": False}


def assess_output(output, payload):
    family, group, ids = validate_payload(payload)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(build_format(group, family)["schema"]).iter_errors(output)]
    raw = output if isinstance(output, dict) else {}
    body = raw.get("result", {}) if isinstance(raw.get("result", {}), dict) else {}
    raw_proofs, pool, pool_audits, global_errors = _pool(output, payload)
    canonical = {"task": raw.get("task"), "result": {"job_family": body.get("job_family")}, "proofs": []}
    used, facts, raw_children, conditional = set(), {}, {}, {}
    for sid in ids:
        record = body.get(sid, {}) if isinstance(body.get(sid, {}), dict) else {}
        if sid not in TARGETS:
            criteria = record.get("criteria", [])
            canonical["result"][sid] = {"criteria": deepcopy(criteria)}
            if isinstance(criteria, list):
                for criterion in criteria:
                    used.update(pid for pid in _refs(criterion) if isinstance(pid, str))
            continue
        fact = record.get("core_facts", {}) if isinstance(record.get("core_facts", {}), dict) else {}
        facts[sid] = _fact_audit(sid, fact, payload, pool)
        used.update(pid for pid in _refs(fact) if isinstance(pid, str))
        status = facts[sid]["mapped_status"]
        children = record.get("children")
        raw_children[sid] = deepcopy(children)
        shape_ok = ((isinstance(children, dict) and set(children) == {"c2", "c3"}) if status == "supported"
                    else "children" in record and children is None)
        conditional[sid] = [] if shape_ok else ["conditional_child_shape_invalid"]
        if isinstance(children, dict):
            child_rows = []
            for cid in ("c2", "c3"):
                child = children.get(cid)
                child_rows.append({**deepcopy(child), "criterion_id": cid} if isinstance(child, dict) else child)
                used.update(pid for pid in _refs(child) if isinstance(pid, str))
        else:
            child_rows = [{"criterion_id": cid, "status": "not_evidenced", "basis": "none", "proof_ids": []} for cid in ("c2", "c3")]
        mapped = {"criterion_id": "c1", "status": status,
                  "basis": "practice" if status == "supported" else "unclear" if status == "uncertain" else "none",
                  "proof_ids": deepcopy(_refs(fact)) if status != "not_evidenced" else []}
        canonical["result"][sid] = {"criteria": [mapped] + child_rows}
    canonical_refs = {pid for record in canonical["result"].values() if isinstance(record, dict)
                      for criterion in (record.get("criteria", []) if isinstance(record.get("criteria", []), list) else [])
                      for pid in _refs(criterion) if isinstance(pid, str)}
    canonical["proofs"] = [p for p in raw_proofs if isinstance(p, dict) and isinstance(p.get("proof_id"), str) and p["proof_id"] in canonical_refs]
    result = base.assess_output(canonical, _base_payload(payload))
    if schema_errors:
        global_errors.append("response_schema_invalid")
    if set(body) != {"job_family", *ids}:
        global_errors.append("wrong_family_or_skill_scope")
    raw_child_audits = {}
    for row in result["skills"]:
        sid = row["skill_id"]
        errors = list(global_errors)
        if sid in TARGETS:
            errors.extend("fact:" + error for error in facts[sid]["errors"])
            errors.extend(conditional[sid])
            raw_child_audits[sid] = deepcopy(row["criterion_audits"][1:]) if isinstance(raw_children[sid], dict) else []
            if facts[sid]["mapped_status"] == "uncertain" and raw_children[sid] is None:
                for audit in row["criterion_audits"][1:]:
                    audit.update(status="blocked_by_unresolved_core", basis="unassessed", points=None,
                                 reported_status=None, reported_basis=None, proofs=[], errors=["blocked_by_unresolved_core"])
                errors.append("children_blocked_by_unresolved_core")
        row["errors"] = list(dict.fromkeys(row["errors"] + errors))
    validation = result["validation"]
    validation["schema_errors"] = schema_errors
    validation["global_errors"] = list(dict.fromkeys(validation["global_errors"] + global_errors))
    validation.update(raw_proof_pool=pool_audits, raw_unused_proof_ids=sorted(set(pool) - used),
                      conditional_output_errors=conditional, raw_output_modified=False,
                      child_states={sid: "assessed" if facts[sid]["mapped_status"] == "supported" else "blocked_by_unresolved_core" if facts[sid]["mapped_status"] == "uncertain" else "skipped_due_to_absent_core" for sid in TARGETS},
                      semantic_validation_performed=False)
    result.update(contract_version=CONTRACT_VERSION, validation_version=VALIDATION_VERSION,
                  input_sha256=payload["input_sha256"], raw_response_sha256=sha(output),
                  fact_audits=facts, raw_children=raw_children, raw_criterion_judgments=deepcopy(raw_children),
                  raw_child_audits=raw_child_audits)
    return apply_shared_proof_policy(result, output)
