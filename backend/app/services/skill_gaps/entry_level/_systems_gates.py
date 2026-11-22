"""Validate LLM check and retrieval facts against permitted resume sources."""
from __future__ import annotations

from copy import deepcopy
import re

from jsonschema import Draft202012Validator

from app.services.skill_gaps.schema import choice, obj
from app.services.skill_gaps.sources import build_index
from . import _rubric as base

CONTRACT_VERSION = "entry-level-systems-fact-gates.v1"
POLICY_VERSION = "llm-check-rag-core-facts.v1"
VALIDATION_VERSION = "systems-fact-structural-checks.v1"
TASK = base.TASK
sha = base.sha


def _scope(group, family):
    if (group, family) != ("systems", "ai_engineer"):
        raise ValueError("This experimental contract supports AI Engineer Systems only")
    return base._scope(group, family)


def build_payload(original_group_payload, packet, variant="rules"):
    if variant != "rules":
        raise ValueError("The fact intervention uses complete rules only")
    _scope(original_group_payload["evidence_scope"]["branch"], original_group_payload["job_family"])
    payload = base.build_payload(original_group_payload, packet, variant)
    payload["contract_version"] = CONTRACT_VERSION
    payload["systems_fact_policy_version"] = POLICY_VERSION
    payload["input_sha256"] = sha({k: v for k, v in payload.items() if k != "input_sha256"})
    return payload


def _base_payload(payload):
    result = deepcopy(payload)
    result["contract_version"] = base.CONTRACT_VERSION
    result.pop("systems_fact_policy_version", None)
    result["input_sha256"] = sha({k: v for k, v in result.items() if k != "input_sha256"})
    return result


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unknown fact input contract")
    if payload.get("systems_fact_policy_version") != POLICY_VERSION or payload.get("variant") != "rules":
        raise ValueError("Unknown fact policy")
    if payload.get("input_sha256") != sha({k: v for k, v in payload.items() if k != "input_sha256"}):
        raise ValueError("Frozen input fingerprint mismatch")
    _scope(payload["evidence_scope"]["branch"], payload["job_family"])
    return base.validate_payload(_base_payload(payload))


def build_format(group, family):
    _scope(group, family)
    result = deepcopy(base.build_format(group, family))
    result["name"] = "entry_systems_fact_gates_ai_engineer_v1"
    schema = result["schema"]
    refs = {"type": "array", "items": {"type": "string"}, "maxItems": 2}
    text = {"type": "string"}
    llm = obj({
        "event": choice("performed", "purpose", "planned", "prepared", "absent", "ambiguous"),
        "workload_link": choice("same", "other", "unclear", "not_applicable"),
        "action": text, "object": text, "detail": text, "proof_ids": refs,
    })
    rag = obj({
        "personal_retrieval": choice("performed", "others_only", "absent", "ambiguous"),
        "model_generation": choice("explicit", "explicitly_absent", "not_stated", "ambiguous"),
        "retrieval_use": choice("generation_context", "unspecified_output", "search_only", "absent", "ambiguous"),
        "workload_link": choice("same", "other", "unclear", "not_applicable"),
        "proof_ids": refs,
    })
    for sid, key, facts in (("llm", "check_facts", llm), ("rag", "core_facts", rag)):
        item = schema["properties"]["result"]["properties"][sid]
        item["properties"]["criteria"]["minItems"] = 2
        item["properties"]["criteria"]["maxItems"] = 2
        item["properties"][key] = facts
        item["required"].append(key)
    return result


def llm_status(facts):
    event, link = (_string(facts.get(k)) for k in ("event", "workload_link"))
    if event in {"purpose", "planned", "prepared", "absent"} or link == "other":
        return "not_evidenced"
    if event != "performed" or link != "same":
        return "uncertain"
    return "supported" if facts.get("detail") else "partial"


def rag_status(facts):
    retrieval, generation, use, link = (_string(facts.get(k)) for k in
        ("personal_retrieval", "model_generation", "retrieval_use", "workload_link"))
    if retrieval in {"others_only", "absent"} or generation == "explicitly_absent" or use in {"search_only", "absent"} or link == "other":
        return "not_evidenced"
    if (retrieval, generation, use, link) == ("performed", "explicit", "generation_context", "same"):
        return "supported"
    return "uncertain"


def _string(value):
    return value if isinstance(value, str) else None


def _refs(item):
    value = item.get("proof_ids", []) if isinstance(item, dict) else []
    return value if isinstance(value, list) else []


def _fact_audit(facts, sid, cid, payload, pool, index):
    errors, proofs = [], []
    refs = _refs(facts)
    if len(refs) > 2 or any(not isinstance(pid, str) for pid in refs):
        errors.append("invalid_fact_proof_references")
    elif len(set(refs)) != len(refs):
        errors.append("duplicate_fact_proof_reference")
    candidates = payload["fixed_evidence_packets"]["skills"][sid]["criterion_unit_ids"][cid]
    for pid in refs:
        proof = pool.get(pid) if isinstance(pid, str) else None
        if not isinstance(proof, dict):
            errors.append("unknown_fact_proof_id")
            continue
        unit = index.get(proof.get("unit_id")) if isinstance(proof.get("unit_id"), str) else None
        quote = proof.get("quote")
        if unit is None or not isinstance(quote, str) or not quote.strip() or quote not in unit["text"]:
            errors.append("fact_quote_not_exact")
        if proof.get("unit_id") not in candidates:
            errors.append("fact_proof_outside_fixed_criterion_candidates")
        proofs.append(deepcopy(proof))
    status = llm_status(facts) if sid == "llm" else rag_status(facts)
    if sid == "llm":
        event = _string(facts.get("event"))
        if event == "performed":
            action, target = facts.get("action"), facts.get("object")
            if not isinstance(action, str) or not action.strip() or not isinstance(target, str) or not target.strip():
                errors.append("performed_check_requires_action_and_object")
            elif not any(action in p.get("quote", "") and target in p.get("quote", "") for p in proofs if isinstance(p.get("quote"), str)):
                errors.append("action_object_not_in_same_exact_quote")
            detail = facts.get("detail")
            if detail and (not isinstance(detail, str) or not any(detail in p.get("quote", "") for p in proofs if isinstance(p.get("quote"), str))):
                errors.append("check_detail_not_in_exact_quote")
            if facts.get("workload_link") == "not_applicable":
                errors.append("performed_check_requires_linkage_state")
        elif any(facts.get(k) for k in ("action", "object", "detail")):
            errors.append("nonperformed_check_has_action_fields")
        if event in {"purpose", "planned", "prepared", "absent"} and facts.get("workload_link") != "not_applicable":
            errors.append("nonperformed_check_requires_not_applicable_link")
        if event == "ambiguous" and facts.get("workload_link") != "unclear":
            errors.append("ambiguous_check_requires_unclear_link")
        if event not in {"absent"} and not refs:
            errors.append("claimed_check_event_without_proof")
    else:
        if any(_string(facts.get(k)) not in absent for k, absent in (
            ("personal_retrieval", {"absent"}), ("model_generation", {"not_stated"}),
            ("retrieval_use", {"absent"}), ("workload_link", {"not_applicable"}))) and not refs:
            errors.append("claimed_retrieval_facts_without_proof")
        if facts.get("retrieval_use") == "generation_context" and (
            facts.get("personal_retrieval") != "performed" or facts.get("model_generation") != "explicit"):
            errors.append("contradictory_generation_context_facts")
        if facts.get("retrieval_use") == "unspecified_output" and facts.get("model_generation") == "not_stated" and facts.get("workload_link") != "unclear":
            errors.append("unstated_generator_requires_unclear_link")
    if status in {"supported", "partial"}:
        if not refs:
            errors.append("positive_fact_mapping_without_proof")
        for proof in proofs:
            unit = index.get(proof.get("unit_id")) if isinstance(proof.get("unit_id"), str) else None
            if unit is not None and unit["kind"] != "claim":
                errors.append("ineligible_fact_practice_source_kind")
    return {"raw_facts": deepcopy(facts), "mapped_status": status,
            "proofs": proofs, "errors": list(dict.fromkeys(errors)),
            "semantic_truth_verified": False}


def assess_output(output, payload):
    family, group, ids = validate_payload(payload)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(build_format(group, family)["schema"]).iter_errors(output)]
    raw = output if isinstance(output, dict) else {}
    body = raw.get("result", {}) if isinstance(raw.get("result", {}), dict) else {}
    proofs = raw.get("proofs", []) if isinstance(raw.get("proofs", []), list) else []
    pool, global_errors, spans, raw_pool_audit = {}, [], set(), []
    index = build_index(payload["resume_sources"])
    for proof in proofs:
        if not isinstance(proof, dict) or not isinstance(proof.get("proof_id"), str):
            continue
        pid = proof["proof_id"]
        proof_errors = []
        if pid in pool:
            global_errors.append("duplicate_proof_id")
        if not re.fullmatch(r"p[1-9][0-9]*", pid):
            global_errors.append("invalid_proof_id")
        unit = index.get(proof.get("unit_id")) if isinstance(proof.get("unit_id"), str) else None
        quote = proof.get("quote")
        if unit is None:
            proof_errors.append("unknown_source_unit")
        if not isinstance(quote, str) or not quote.strip() or (unit is not None and quote not in unit["text"]):
            proof_errors.append("quote_not_exact")
        if isinstance(proof.get("unit_id"), str) and isinstance(proof.get("quote"), str):
            span = (proof["unit_id"], proof["quote"])
            if span in spans:
                global_errors.append("duplicate_proof_span")
            spans.add(span)
        pool[pid] = proof
        raw_pool_audit.append({**deepcopy(proof), "errors": proof_errors})
    canonical = {"task": raw.get("task"), "proofs": deepcopy(proofs), "result": {"job_family": body.get("job_family")}}
    used = set()
    facts, raw_children = {}, {}
    raw_child_errors = []
    for sid in ids:
        value = body.get(sid, {}) if isinstance(body.get(sid, {}), dict) else {}
        criteria = value.get("criteria", []) if isinstance(value.get("criteria", []), list) else []
        for criterion in criteria:
            used.update(pid for pid in _refs(criterion) if isinstance(pid, str))
            if sid == "rag" and isinstance(criterion, dict):
                cid = criterion.get("criterion_id")
                for pid in _refs(criterion):
                    proof = pool.get(pid) if isinstance(pid, str) else None
                    if proof is None:
                        raw_child_errors.append("unknown_raw_child_proof_id")
                    elif isinstance(cid, str) and proof.get("unit_id") not in payload["fixed_evidence_packets"]["skills"][sid]["criterion_unit_ids"].get(cid, []):
                        raw_child_errors.append("raw_child_proof_outside_fixed_criterion_candidates")
        if sid in {"llm", "rag"}:
            cid, key = ("c3", "check_facts") if sid == "llm" else ("c1", "core_facts")
            fact = value.get(key, {}) if isinstance(value.get(key, {}), dict) else {}
            used.update(pid for pid in _refs(fact) if isinstance(pid, str))
            facts[sid] = _fact_audit(fact, sid, cid, payload, pool, index)
            raw_children[sid] = deepcopy(criteria)
            expected = ["c1", "c2"] if sid == "llm" else ["c2", "c3"]
            if [c.get("criterion_id") if isinstance(c, dict) else None for c in criteria] != expected:
                facts[sid]["errors"].append("fact_skill_criterion_ids_invalid")
            status = facts[sid]["mapped_status"]
            mapped = {"criterion_id": cid, "status": status,
                      "basis": "practice" if status in {"supported", "partial"} else "unclear" if status == "uncertain" else "none",
                      "proof_ids": deepcopy(_refs(fact)) if status != "not_evidenced" else []}
            criteria = deepcopy(criteria)
            if sid == "rag" and status == "uncertain":
                criteria = [{"criterion_id": c, "status": "not_evidenced", "basis": "none", "proof_ids": []} for c in ("c2", "c3")]
            criteria = criteria + [mapped] if sid == "llm" else [mapped] + criteria
        canonical["result"][sid] = {"criteria": deepcopy(criteria)}
    unused = sorted(set(pool) - used)
    if unused:
        global_errors.append("unused_proofs")
    if set(body) != {"job_family", *ids}:
        global_errors.append("wrong_family_or_skill_scope")
    raw_child_audits = []
    if facts["rag"]["mapped_status"] == "uncertain":
        raw_projection = deepcopy(canonical)
        raw_projection["result"]["rag"]["criteria"] = [raw_projection["result"]["rag"]["criteria"][0]] + deepcopy(raw_children["rag"])
        raw_refs = {pid for item in raw_projection["result"].values() if isinstance(item, dict)
                    for criterion in item.get("criteria", []) for pid in _refs(criterion) if isinstance(pid, str)}
        raw_projection["proofs"] = [p for p in proofs if isinstance(p, dict) and isinstance(p.get("proof_id"), str) and p["proof_id"] in raw_refs]
        raw_assessment = base.assess_output(raw_projection, _base_payload(payload))
        raw_rag = next(row for row in raw_assessment["skills"] if row["skill_id"] == "rag")
        raw_child_audits = deepcopy(raw_rag["criterion_audits"][1:])
        expected_dependency_errors = {"criterion_uncertain", "dependent_credit_without_resolved_personal_core"}
        for audit in raw_child_audits:
            raw_child_errors.extend(f"raw_{audit['criterion_id']}:{error}" for error in audit["errors"] if error not in expected_dependency_errors)
    canonical_refs = {pid for item in canonical["result"].values() if isinstance(item, dict)
                      for criterion in item.get("criteria", []) for pid in _refs(criterion) if isinstance(pid, str)}
    # Fact-only negative proofs and blocked children are still validated/audited
    # here; the legacy arithmetic receives only proofs it can reference.
    canonical["proofs"] = [p for p in proofs if isinstance(p, dict) and isinstance(p.get("proof_id"), str) and p["proof_id"] in canonical_refs]
    assessment = base.assess_output(canonical, _base_payload(payload))
    if schema_errors:
        global_errors.append("response_schema_invalid")
    for row in assessment["skills"]:
        sid = row["skill_id"]
        errors = list(global_errors)
        if sid in facts:
            errors.extend("fact:" + error for error in facts[sid]["errors"])
        if sid == "rag":
            errors.extend(raw_child_errors)
        if sid == "rag" and facts[sid]["mapped_status"] == "uncertain":
            for audit in row["criterion_audits"][1:]:
                audit.update(status="blocked_by_unresolved_core", basis="unassessed", points=None,
                             reported_status=None, reported_basis=None, proofs=[],
                             errors=["blocked_by_unresolved_core"])
            errors.append("children_blocked_by_unresolved_core")
        if errors:
            row["errors"] = list(dict.fromkeys(row["errors"] + errors))
            row.update(entry_level_score=None, entry_level_gap=None, entry_level_grade=base.grade(None),
                       calculation_state="needs_confirmation", critical_cap_applied=False)
    assessment.update(contract_version=CONTRACT_VERSION, validation_version=VALIDATION_VERSION,
                      input_sha256=payload["input_sha256"], fact_audits=facts,
                      raw_criterion_judgments=raw_children,
                      raw_child_validation_errors=list(dict.fromkeys(raw_child_errors)),
                      raw_blocked_child_audits=raw_child_audits,
                      unscored_skill_ids=[r["skill_id"] for r in assessment["skills"] if r["entry_level_score"] is None])
    validation = assessment["validation"]
    validation["schema_errors"] = schema_errors
    validation["global_errors"] = list(dict.fromkeys(validation["global_errors"] + global_errors))
    validation.update(raw_proof_count=len(proofs), raw_unused_proof_ids=unused,
                      raw_proof_pool=raw_pool_audit,
                      deterministic_fact_mapping=True, dependency_normalization_reported_separately=True,
                      semantic_validation_performed=False)
    return assessment
