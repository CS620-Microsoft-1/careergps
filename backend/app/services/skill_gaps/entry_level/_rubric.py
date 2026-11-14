"""Validate fixed evidence and calculate the entry-level rubric."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.schema import choice, obj
from app.services.skill_gaps.skill_groups import GROUPS, GROUP_SKILLS
from app.services.skill_gaps.sources import build_index
from app.services.skill_gaps.scoring_math import grade

RULES = Path(__file__).with_name("data")
TASK = "assess_entry_level_readiness"
CONTRACT_VERSION = "entry-level-fixed-rule-assessment.v2"
PACKET_VERSION = "fixed-criterion-source-packet.v1"
VALIDATION_VERSION = "fixed-source-rule-policy-checks.v2"
VARIANTS = ("rules",)
CRITERION_IDS = ("c1", "c2", "c3")
POINTS = {"supported": Decimal(1), "partial": Decimal("0.5"), "not_evidenced": Decimal(0)}




def sha(value):
    """Hash the canonical representation shared with the versioned input protocol."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _scope(group, family):
    if group not in GROUPS or family not in GROUP_SKILLS:
        raise ValueError("Unknown skill group or family")
    assigned = set(GROUP_SKILLS[family][group])
    # The application preserves catalog order; its assignment tuples are sets
    # of ownership and differ in order for Data Analyst Foundation.
    return [sid for sid in _catalog(family) if sid in assigned]






@lru_cache(maxsize=3)
def _catalog(family):
    data = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8-sig"))
    return {
        skill["skill_id"]: {**skill, "module_id": module["module_id"], "module_name": module["module_name"]}
        for module in data["families"][family]["modules"] for skill in module["skills"]
    }


@lru_cache(maxsize=3)
def _rule_document(family):
    if family not in GROUP_SKILLS:
        raise ValueError("Unknown skill family")
    return json.loads((RULES / f"{family}.json").read_text(encoding="ascii"))


def _rule_cards(group, family, variant):
    if variant not in VARIANTS:
        raise ValueError("Unknown skill rule variant")
    document = _rule_document(family)
    return document["rule_version"], {sid: deepcopy(document["skills"][sid]) for sid in _scope(group, family)}


def build_format(group, family):
    """Build the strict result schema for this family and group."""
    ids = _scope(group, family)
    proof = obj({"proof_id": {"type": "string"}, "unit_id": {"type": "string"}, "quote": {"type": "string"}})
    criterion = obj({
        "criterion_id": choice(*CRITERION_IDS),
        "status": choice("supported", "partial", "not_evidenced", "uncertain"),
        "basis": choice("practice", "knowledge", "unclear", "none"),
        "proof_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
    })
    result = {"job_family": choice(family)}
    result.update({sid: obj({"criteria": {"type": "array", "items": {"$ref": "#/$defs/Criterion"},
                                          "minItems": 3, "maxItems": 3}}) for sid in ids})
    schema = obj({"task": choice(TASK),
                  "proofs": {"type": "array", "items": {"$ref": "#/$defs/Proof"}, "maxItems": 6 * len(ids)},
                  "result": obj(result)})
    schema["$defs"] = {"Proof": proof, "Criterion": criterion}
    return {"name": f"entry_fixed_{family}_{group}_v1", "strict": True, "schema": schema}




def _string_list(value, label):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value) or len(value) != len(set(value)):
        raise ValueError(f"{label} must contain unique nonempty string IDs")
    return value


def _project_packet(packet, sources, ids, family, rule_cards, *, check_source_hash):
    if not isinstance(packet, dict) or packet.get("version") != PACKET_VERSION or packet.get("job_family") != family:
        raise ValueError("Packet version or family mismatch")
    if check_source_hash and packet.get("source_sha256") != sha(sources):
        raise ValueError("Packet source_sha256 does not match original sources")
    index = build_index(sources)
    original_order = list(index)
    activities = {s["id"]: s for s in sources}
    raw_skills = packet.get("skills")
    if not isinstance(raw_skills, dict) or not set(ids) <= set(raw_skills):
        raise ValueError("Fixed packet is missing assigned skills")
    family_ids = {s for values in GROUP_SKILLS[family].values() for s in values}
    if not set(raw_skills) <= family_ids:
        raise ValueError("Fixed packet contains unknown family skills")
    selected = {}
    for sid in ids:
        item = raw_skills[sid]
        if not isinstance(item, dict):
            raise ValueError("Each fixed skill packet must be an object")
        units = _string_list(item.get("unit_ids"), f"{sid}.unit_ids")
        if any(uid not in index for uid in units):
            raise ValueError("Packet references an unknown source unit")
        if units != [uid for uid in original_order if uid in units]:
            raise ValueError("Packet must preserve original source-unit order")
        activity_ids = {index[uid]["activity_id"] for uid in units}
        complete = [u["id"] for s in sources if s["id"] in activity_ids for u in s["units"]]
        if units != complete:
            raise ValueError("Selected activities must retain all original units and context")
        linkage = item.get("linkage_policy")
        if linkage != rule_cards[sid]["linkage_policy"]:
            raise ValueError("Packet linkage policy differs from skill rule")
        workload = item.get("workload_id")
        if not isinstance(workload, str) or not workload.strip():
            raise ValueError("Every packet needs an opaque workload/concept ID")
        candidate = item.get("criterion_unit_ids")
        if not isinstance(candidate, dict) or set(candidate) != set(CRITERION_IDS):
            raise ValueError("Every packet needs exactly c1, c2 and c3 candidate lists")
        for cid in CRITERION_IDS:
            refs = _string_list(candidate[cid], f"{sid}.{cid}")
            if any(uid not in units for uid in refs):
                raise ValueError("Criterion candidates must be inside the complete skill packet")
            if refs != [uid for uid in units if uid in refs]:
                raise ValueError("Criterion candidates must preserve original unit order")
        selected[sid] = {"unit_ids": deepcopy(units), "criterion_unit_ids": deepcopy(candidate),
                         "linkage_policy": linkage, "workload_id": workload}
    selected_activity_ids = {index[uid]["activity_id"] for item in selected.values() for uid in item["unit_ids"]}
    retained = [deepcopy(s) for s in sources if s["id"] in selected_activity_ids]
    return selected, retained


def build_payload(original_group_payload, packet, variant="rules"):
    family = original_group_payload["job_family"]
    group = original_group_payload["evidence_scope"]["branch"]
    ids = _scope(group, family)
    if original_group_payload["evidence_scope"]["assigned_skill_ids"] != ids:
        raise ValueError("Original group assignment differs from the frozen partition")
    version, cards = _rule_cards(group, family, variant)
    selected, sources = _project_packet(packet, original_group_payload["resume_sources"], ids, family, cards, check_source_hash=True)
    catalog = _catalog(family)
    original_cores = {c["skill_id"]: c for c in original_group_payload["core_skills"]}
    if set(original_cores) != set(ids):
        raise ValueError("Original core skills differ from the group scope")
    # Copy owning catalog definitions rather than trusting caller-supplied edits.
    for sid in ids:
        for key, value in original_cores[sid].items():
            if key in catalog[sid] and value != catalog[sid][key]:
                raise ValueError("Original core card differs from the owning catalog")
    payload = {"task": TASK, "contract_version": CONTRACT_VERSION, "variant": variant,
               "job_family": family, "evidence_scope": {"branch": group, "assigned_skill_ids": ids},
               "core_skills": [catalog[sid] for sid in ids], "rule_catalog_version": version,
               "skill_rules": cards, "resume_sources": sources,
               "fixed_evidence_packets": {"version": PACKET_VERSION, "job_family": family,
                   "source_sha256": sha(sources), "skills": selected},
               "original_resume_sources_sha256": packet["source_sha256"]}
    payload["rule_cards_sha256"] = sha(cards)
    payload["evidence_sha256"] = sha({"resume_sources": sources, "skills": selected})
    payload["input_sha256"] = sha(payload)
    return payload


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("task") != TASK or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unknown input contract")
    frozen = {key: value for key, value in payload.items() if key != "input_sha256"}
    if payload.get("input_sha256") != sha(frozen):
        raise ValueError("Frozen input fingerprint mismatch")
    family, group, variant = payload["job_family"], payload["evidence_scope"]["branch"], payload["variant"]
    ids = _scope(group, family)
    if payload["evidence_scope"]["assigned_skill_ids"] != ids:
        raise ValueError("Input skill assignment changed")
    version, cards = _rule_cards(group, family, variant)
    if payload["skill_rules"] != cards or payload["rule_catalog_version"] != version or payload["rule_cards_sha256"] != sha(cards):
        raise ValueError("Input rules differ from the frozen catalog")
    catalog = _catalog(family)
    if payload["core_skills"] != [catalog[sid] for sid in ids]:
        raise ValueError("Input core definitions changed")
    selected, sources = _project_packet(payload["fixed_evidence_packets"], payload["resume_sources"], ids, family, cards, check_source_hash=True)
    if selected != payload["fixed_evidence_packets"]["skills"] or sources != payload["resume_sources"]:
        raise ValueError("Input contains unselected sources or packet annotations")
    if payload["evidence_sha256"] != sha({"resume_sources": sources, "skills": selected}):
        raise ValueError("Fixed evidence fingerprint mismatch")
    return family, group, ids


def assess_output(output, payload):
    """Preserve reported labels; invalid or uncertain skills remain pending."""
    family, group, ids = validate_payload(payload)
    schema = build_format(group, family)["schema"]
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(schema).iter_errors(output)]
    index = build_index(payload["resume_sources"])
    body = output.get("result", {}) if isinstance(output, dict) else {}
    body = body if isinstance(body, dict) else {}
    raw_proofs = output.get("proofs", []) if isinstance(output, dict) else []
    raw_proofs = raw_proofs if isinstance(raw_proofs, list) else []
    pool, pool_errors, proof_audit, span_ids = {}, {}, [], {}
    global_errors = ["response_schema_invalid"] if schema_errors else []
    for proof in raw_proofs:
        if not isinstance(proof, dict) or not isinstance(proof.get("proof_id"), str):
            continue
        pid, uid, quote = proof["proof_id"], proof.get("unit_id"), proof.get("quote")
        errors = []
        if not re.fullmatch(r"p[1-9][0-9]*", pid):
            errors.append("invalid_proof_id")
        if pid in pool:
            global_errors.append("duplicate_proof_id")
            pool_errors[pid] = list(dict.fromkeys(pool_errors[pid] + ["duplicate_proof_id"]))
            proof_audit.append({"proof_id": pid, "unit_id": uid, "errors": ["duplicate_proof_id"]})
            continue
        unit = index.get(uid) if isinstance(uid, str) else None
        if unit is None:
            errors.append("unknown_source_unit")
        if not isinstance(quote, str) or not quote.strip() or (unit is not None and quote not in unit["text"]):
            errors.append("quote_not_exact")
        if isinstance(uid, str) and isinstance(quote, str):
            key = (uid, quote)
            if key in span_ids:
                global_errors.append("duplicate_proof_span")
            else:
                span_ids[key] = pid
        pool[pid] = {"proof_id": pid, "unit_id": uid, "quote": quote,
                     "activity_id": unit["activity_id"] if unit else None, "kind": unit["kind"] if unit else None}
        pool_errors[pid] = errors
        proof_audit.append({**pool[pid], "errors": errors})
    used = set()
    for sid in ids:
        record = body.get(sid)
        records = record.get("criteria", []) if isinstance(record, dict) else []
        if isinstance(records, list):
            for record in records:
                refs = record.get("proof_ids", []) if isinstance(record, dict) else []
                if isinstance(refs, list):
                    used.update(pid for pid in refs if isinstance(pid, str))
    unused = sorted(set(pool) - used)
    if unused:
        global_errors.append("unused_proofs")
    if body.get("job_family") != family or set(body) != {"job_family", *ids}:
        global_errors.append("wrong_family_or_skill_scope")
    rows = []
    catalog = _catalog(family)
    for sid in ids:
        card = payload["skill_rules"][sid]
        packet = payload["fixed_evidence_packets"]["skills"][sid]
        record = body.get(sid)
        observed = record.get("criteria", []) if isinstance(record, dict) else []
        observed = observed if isinstance(observed, list) else []
        errors = list(dict.fromkeys(global_errors))
        if [c.get("criterion_id") if isinstance(c, dict) else None for c in observed] != list(CRITERION_IDS):
            errors.append("criterion_ids_missing_duplicate_or_out_of_order")
        by_id = {c.get("criterion_id"): c for c in observed if isinstance(c, dict) and isinstance(c.get("criterion_id"), str)}
        audits, weighted = [], Decimal(0)
        for criterion in card["criteria"]:
            cid = criterion["id"]
            item = by_id.get(cid, {})
            reported_status, reported_basis = item.get("status"), item.get("basis")
            status = reported_status if isinstance(reported_status, str) else None
            basis = reported_basis if isinstance(reported_basis, str) else None
            refs = item.get("proof_ids", [])
            refs = refs if isinstance(refs, list) else []
            issues, proofs = [], []
            if not isinstance(reported_status, str):
                issues.append("criterion_status_not_string")
            if not isinstance(reported_basis, str):
                issues.append("criterion_basis_not_string")
            positive = status in {"supported", "partial"}
            if status == "uncertain":
                issues.append("criterion_uncertain")
                if basis != "unclear":
                    issues.append("uncertain_requires_unclear_basis")
            elif status not in POINTS:
                issues.append("invalid_criterion_status")
            if payload["variant"] == "rules" and status == "partial" and not criterion["partial_allowed"]:
                issues.append("partial_disabled_by_rule")
            if len(refs) > 2 or any(not isinstance(pid, str) for pid in refs):
                issues.append("invalid_proof_reference_list")
            elif len(set(refs)) != len(refs):
                issues.append("duplicate_proof_reference")
            if positive and not refs:
                issues.append("positive_without_proof")
            if status == "not_evidenced" and (refs or basis != "none"):
                issues.append("not_evidenced_requires_none_and_no_proofs")
            if positive and basis not in {"practice", "knowledge"}:
                issues.append("positive_basis_unresolved")
            if positive and criterion["minimum_evidence"] == "practice" and basis != "practice":
                issues.append("practice_basis_required")
            for pid in refs:
                if not isinstance(pid, str):
                    continue
                if pid not in pool:
                    issues.append("unknown_proof_id")
                    continue
                proof = pool[pid]
                proofs.append(deepcopy(proof))
                issues.extend(pool_errors[pid])
                if proof["unit_id"] not in packet["criterion_unit_ids"][cid]:
                    issues.append("proof_outside_fixed_criterion_candidates")
                if positive:
                    allowed = {"claim"} if basis == "practice" else {"claim", "listed"}
                    if proof["kind"] not in allowed:
                        issues.append("ineligible_positive_source_kind")
            point = POINTS.get(status)
            if point is not None:
                weighted += Decimal(str(criterion["weight"])) * point
            audits.append({"criterion_id": cid, "status": status, "basis": basis,
                           "reported_status": deepcopy(reported_status), "reported_basis": deepcopy(reported_basis),
                           "weight": criterion["weight"], "critical": criterion["critical"],
                           "points": None if point is None else float(point),
                           "proofs": proofs, "errors": list(dict.fromkeys(issues))})
        if card["linkage_policy"] == "same_personal_example":
            core = audits[0]
            for audit in audits[1:]:
                if core["status"] == "not_evidenced" and audit["status"] != "not_evidenced":
                    audit["errors"].append("dependent_criterion_without_practice_core")
                elif audit["status"] in {"supported", "partial"} and (core["status"] not in {"supported", "partial"} or core["basis"] != "practice"):
                    audit["errors"].append("dependent_credit_without_resolved_personal_core")
        for audit in audits:
            errors.extend(f"{audit['criterion_id']}:{error}" for error in audit["errors"])
        errors = list(dict.fromkeys(errors))
        capped = not errors and audits[0]["status"] != "supported" and weighted > Decimal("0.6")
        if capped:
            weighted = Decimal("0.6")
        score = None if errors else weighted
        gap = None if score is None else Decimal(1) - score
        rows.append({"skill_id": sid, "skill_name": catalog[sid]["skill_name"],
                     "module_id": catalog[sid]["module_id"], "module_name": catalog[sid]["module_name"],
                     "entry_level_score": None if score is None else float(score),
                     "entry_level_gap": None if gap is None else float(gap),
                     "entry_level_grade": grade(gap), "calculation_state": "needs_confirmation" if errors else "scored",
                     "critical_cap_applied": capped, "criterion_audits": audits, "errors": errors})
    return {"task": TASK, "contract_version": CONTRACT_VERSION, "validation_version": VALIDATION_VERSION,
            "variant": payload["variant"], "job_family": family, "branch": group,
            "rule_catalog_version": payload["rule_catalog_version"], "input_sha256": payload["input_sha256"],
            "evidence_sha256": payload["evidence_sha256"], "skills": rows,
            "unscored_skill_ids": [row["skill_id"] for row in rows if row["entry_level_score"] is None],
            "validation": {"schema_errors": schema_errors, "global_errors": list(dict.fromkeys(global_errors)),
                "proof_pool": proof_audit, "unused_proof_ids": unused, "proof_count": len(raw_proofs),
                "criterion_count": 3 * len(ids), "fixed_criterion_permissions_checked": True,
                "source_selection_semantics_verified": False, "semantic_validation_performed": False,
                "partial_policy_enforced": payload["variant"] == "rules", "automatic_repairs": False}}


score_response = assess_output
