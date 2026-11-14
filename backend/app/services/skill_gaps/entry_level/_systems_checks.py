"""Validate identified model outputs and fixed RAG child fields."""
from __future__ import annotations

from copy import deepcopy

from jsonschema import Draft202012Validator

from app.services.skill_gaps.schema import obj
from app.services.skill_gaps.sources import build_index
from . import _systems_facts as previous

base = previous.base
sha = previous.sha
TASK = previous.TASK
CONTRACT_VERSION = "entry-level-systems-fixed-fields.v1"
POLICY_VERSION = "checked-output-nullable-rag-children.v1"
VALIDATION_VERSION = "systems-fixed-field-validation.v1"
rag_status = previous.rag_status


def build_payload(original_group_payload, packet, variant="rules"):
    payload = previous.build_payload(original_group_payload, packet, variant)
    payload["contract_version"] = CONTRACT_VERSION
    payload["systems_fact_policy_version"] = POLICY_VERSION
    payload["input_sha256"] = sha({k: v for k, v in payload.items() if k != "input_sha256"})
    return payload


def _previous_payload(payload):
    result = deepcopy(payload)
    result["contract_version"] = previous.CONTRACT_VERSION
    result["systems_fact_policy_version"] = previous.POLICY_VERSION
    result["input_sha256"] = sha({k: v for k, v in result.items() if k != "input_sha256"})
    return result


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unknown fixed-field input contract")
    if payload.get("systems_fact_policy_version") != POLICY_VERSION:
        raise ValueError("Unknown fixed-field policy")
    if payload.get("input_sha256") != sha({k: v for k, v in payload.items() if k != "input_sha256"}):
        raise ValueError("Frozen input fingerprint mismatch")
    return previous.validate_payload(_previous_payload(payload))


def build_format(group, family):
    result = deepcopy(previous.build_format(group, family))
    result["name"] = "entry_systems_fixed_fields_ai_engineer_v1"
    schema = result["schema"]
    facts = schema["properties"]["result"]["properties"]["llm"]["properties"]["check_facts"]
    facts["properties"] = {("checked_output" if key == "object" else key): value for key, value in facts["properties"].items()}
    facts["required"] = ["checked_output" if key == "object" else key for key in facts["required"]]
    child = deepcopy(schema["$defs"]["Criterion"])
    child["properties"].pop("criterion_id")
    child["required"].remove("criterion_id")
    schema["$defs"]["RagChild"] = child
    rag = schema["properties"]["result"]["properties"]["rag"]
    rag["properties"] = {"core_facts": rag["properties"]["core_facts"],
                         "children": {"anyOf": [{"type": "null"}, obj({
                             "c2": {"$ref": "#/$defs/RagChild"},
                             "c3": {"$ref": "#/$defs/RagChild"},
                         })]}}
    rag["required"] = ["core_facts", "children"]
    return result


def llm_status(facts):
    mapped = previous.llm_status(facts)
    if facts.get("event") == "performed" and facts.get("checked_output") == "" and facts.get("workload_link") != "other":
        return "uncertain"
    return mapped


def _project_output(output, core_status):
    projected = deepcopy(output)
    if not isinstance(projected, dict) or not isinstance(projected.get("result"), dict):
        return projected
    body = projected["result"]
    llm = body.get("llm")
    if isinstance(llm, dict) and isinstance(llm.get("check_facts"), dict):
        facts = llm["check_facts"]
        facts["object"] = facts.pop("checked_output", None)
    rag = body.get("rag")
    if isinstance(rag, dict):
        children = rag.pop("children", None)
        if isinstance(children, dict):
            rag["criteria"] = [({"criterion_id": cid, **children[cid]} if isinstance(children.get(cid), dict) else children.get(cid))
                               for cid in ("c2", "c3")]
        elif children is None and core_status == "not_evidenced":
            rag["criteria"] = [{"criterion_id": cid, "status": "not_evidenced", "basis": "none", "proof_ids": []}
                               for cid in ("c2", "c3")]
        else:
            rag["criteria"] = []
    return projected


def assess_output(output, payload):
    family, group, _ = validate_payload(payload)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(build_format(group, family)["schema"]).iter_errors(output)]
    raw = output if isinstance(output, dict) else {}
    body = raw.get("result", {}) if isinstance(raw.get("result", {}), dict) else {}
    rag = body.get("rag", {}) if isinstance(body.get("rag", {}), dict) else {}
    rag_facts = rag.get("core_facts", {}) if isinstance(rag.get("core_facts", {}), dict) else {}
    core_status = rag_status(rag_facts)
    children = rag.get("children")
    child_shape_valid = ((isinstance(children, dict) and set(children) == {"c2", "c3"}) if core_status == "supported"
                         else "children" in rag and children is None)
    conditional_errors = [] if child_shape_valid else ["rag_conditional_child_shape_invalid"]
    projected = _project_output(output, core_status)
    assessment = previous.assess_output(projected, _previous_payload(payload))
    llm_record = body.get("llm", {}) if isinstance(body.get("llm", {}), dict) else {}
    facts = llm_record.get("check_facts", {}) if isinstance(llm_record.get("check_facts", {}), dict) else {}
    audit = assessment["fact_audits"]["llm"]
    audit["raw_facts"] = deepcopy(facts)
    audit["semantic_pending_reasons"] = []
    target_unknown = facts.get("event") == "performed" and facts.get("checked_output") == ""
    if target_unknown:
        action = facts.get("action")
        valid_action = isinstance(action, str) and bool(action.strip()) and any(
            isinstance(p.get("quote"), str) and action in p["quote"] for p in audit["proofs"])
        if valid_action:
            audit["errors"] = [e for e in audit["errors"] if e != "performed_check_requires_action_and_object"]
        elif isinstance(action, str) and action.strip():
            audit["errors"].append("check_action_not_in_exact_quote")
        if facts.get("detail"):
            audit["errors"].append("unidentified_output_requires_empty_detail")
        index = build_index(payload["resume_sources"])
        for proof in audit["proofs"]:
            unit = index.get(proof.get("unit_id")) if isinstance(proof.get("unit_id"), str) else None
            if unit is not None and unit["kind"] != "claim":
                audit["errors"].append("performed_fact_requires_claim_source")
        audit["errors"] = list(dict.fromkeys(audit["errors"]))
        mapped = llm_status(facts)
        audit["mapped_status"] = mapped
        if mapped == "uncertain":
            audit["semantic_pending_reasons"] = ["checked_output_unidentified"]
        row = next(r for r in assessment["skills"] if r["skill_id"] == "llm")
        c3 = row["criterion_audits"][2]
        criterion_errors = ["criterion_uncertain"] if mapped == "uncertain" else []
        if row["criterion_audits"][0]["status"] == "not_evidenced" and mapped != "not_evidenced":
            criterion_errors.append("dependent_criterion_without_practice_core")
        proof_rows = []
        if mapped != "not_evidenced":
            for proof in audit["proofs"]:
                unit = index.get(proof.get("unit_id")) if isinstance(proof.get("unit_id"), str) else None
                proof_rows.append({**deepcopy(proof), "activity_id": unit["activity_id"] if unit else None,
                                   "kind": unit["kind"] if unit else None})
        c3.update(status=mapped, basis="unclear" if mapped == "uncertain" else "none",
                  reported_status=mapped, reported_basis="unclear" if mapped == "uncertain" else "none",
                  points=None if mapped == "uncertain" else 0.0, proofs=proof_rows, errors=criterion_errors)
        row["errors"] = [e for e in row["errors"] if not e.startswith("c3:") and not e.startswith("fact:")]
        row["errors"].extend("c3:" + e for e in criterion_errors)
        row["errors"].extend("fact:" + e for e in audit["errors"])
    assessment["raw_rag_children"] = deepcopy(children)
    assessment["raw_criterion_judgments"]["rag"] = deepcopy(children)
    if children is None:
        assessment["raw_blocked_child_audits"] = []
    for row in assessment["skills"]:
        if row["skill_id"] == "rag":
            row["errors"] = list(dict.fromkeys(row["errors"] + conditional_errors))
        if schema_errors and "response_schema_invalid" not in row["errors"]:
            row["errors"].append("response_schema_invalid")
    validation = assessment["validation"]
    validation["schema_errors"] = schema_errors
    validation["conditional_output_errors"] = list(dict.fromkeys(validation.get("conditional_output_errors", []) + conditional_errors))
    if schema_errors and "response_schema_invalid" not in validation["global_errors"]:
        validation["global_errors"].append("response_schema_invalid")
    validation.update(raw_output_modified=False, fixed_rag_children=True,
                      child_state="assessed" if core_status == "supported" else "blocked_by_unresolved_core" if core_status == "uncertain" else "skipped_due_to_absent_core",
                      rag_child_judgments_emitted_by_model=isinstance(children, dict),
                      absent_core_children_are_dependency_derived=core_status == "not_evidenced" and children is None)
    assessment.update(contract_version=CONTRACT_VERSION, validation_version=VALIDATION_VERSION,
                      input_sha256=payload["input_sha256"], raw_response_sha256=sha(output),
                      semantic_pending_reasons={"llm": audit["semantic_pending_reasons"]})
    previous._refresh_scores(assessment)
    return assessment
