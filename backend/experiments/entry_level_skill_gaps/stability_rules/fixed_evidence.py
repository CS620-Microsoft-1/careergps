"""Fixed activity/core-anchor protocol layered on the unchanged compact v2 scorer.

This is an experimental input restriction, not a new scoring policy. A packet
does not assert that its selected evidence qualifies. c2/c3 source selection and
all semantic judgments remain model decisions inside the fixed activity.
Compliance is reported separately and never rewrites a response or its score.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from ..entry_agents import compact_contract as compact
from app.services.skill_gaps.sources import build_index

PROTOCOL_VERSION = "fixed-activity-core-anchor.v1"
PACKET_FIELDS = ("activity_id", "unit_ids", "anchor_unit_ids")
SELECTION_SCOPE = "fixed_activity_and_c1_anchor_residual_c2_c3_unit_and_quote_selection"

# Exactly the existing response schema, numeric policy and semantic-free scorer.
build_format = compact.build_format
assess_output = compact.assess_output
POLICY = compact.POLICY
VALIDATION_VERSION = compact.VALIDATION_VERSION


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_instructions(group):
    """Change selection scope only; retain compact v2 criterion judgments."""
    old = compact.build_instructions(group)
    old_opening = "Read the complete supplied resume_sources once, map relevant evidence to the assigned skills, then return only their supplied criteria."
    new_opening = "Read the supplied complete activities once and assess each skill only within its fixed_evidence_packets entry, then return only its supplied criteria."
    old_selection = "For practice criteria choose one coherent personal example per skill."
    new_selection = (
        "Each skill's fixed_evidence_packets entry supplies one selected activity, its permitted unit_ids, "
        "and anchor_unit_ids for the core criterion. Use only that skill's permitted units, even when "
        "another skill's activity appears in resume_sources. Do not select a different activity. "
        "For a supported, partial or uncertain c1, cite at least one supplied anchor unit; another "
        "permitted unit may supply necessary context. A selected anchor is a candidate to assess, "
        "not confirmation of eligibility or a target score. If it does not support the criterion, "
        "use the unchanged not_evidenced/uncertain rules. For c2/c3 choose relevant evidence only "
        "within this same fixed activity; these unit choices and quote spans are not pre-decided."
    )
    old_knowledge = "Independent knowledge criteria can use independently relevant evidence."
    new_knowledge = "Knowledge criteria also use only the corresponding skill's fixed packet; preserve their existing minimum evidence requirements."
    assert old.count(old_opening) == old.count(old_selection) == old.count(old_knowledge) == 1
    return old.replace(old_opening, new_opening).replace(old_selection, new_selection).replace(old_knowledge, new_knowledge)


def _packet_skills(packet, sources, assigned):
    if not isinstance(packet, dict) or not isinstance(packet.get("skills"), dict):
        raise ValueError("A fixed packet requires a skills mapping")
    build_index(sources)
    activities = {source["id"]: source for source in sources}
    if len(activities) != len(sources):
        raise ValueError("Duplicate activity IDs")
    selected = {}
    for skill in assigned:
        item = packet["skills"].get(skill)
        if not isinstance(item, dict) or any(key not in item for key in PACKET_FIELDS):
            raise ValueError(f"Missing fixed packet fields for {skill}")
        activity_id = item["activity_id"]
        if not isinstance(activity_id, str) or activity_id not in activities:
            raise ValueError(f"Unknown fixed activity for {skill}")
        unit_ids, anchors = item["unit_ids"], item["anchor_unit_ids"]
        expected_units = [unit["id"] for unit in activities[activity_id]["units"]]
        if not isinstance(unit_ids, list) or unit_ids != expected_units:
            raise ValueError(f"Packet must retain all units in original activity order: {skill}")
        if (not isinstance(anchors, list) or not anchors
                or any(not isinstance(uid, str) or uid not in unit_ids for uid in anchors)
                or len(anchors) != len(set(anchors))):
            raise ValueError(f"Packet requires nonempty unique anchors inside the activity: {skill}")
        selected[skill] = {key: deepcopy(item[key]) for key in PACKET_FIELDS}
    return selected


def build_payload(original_compact_payload, packet_or_criteria, packet=None):
    """Keep exact source activities/cards and restrict which activity each skill uses.

    Packet notes, expectations, scores, and other metadata are never forwarded.
    The caller owns full-input fingerprint validation because a group payload
    intentionally no longer contains other groups' core cards.

    Preferred API: build_payload(existing_compact_payload, packet). The optional
    three-argument form accepts an original group payload, criteria, and packet
    for local tests; it delegates the initial construction to compact v2.
    """
    if packet is None:
        packet = packet_or_criteria
        result = deepcopy(original_compact_payload)
        if (result.get("task") != compact.TASK
                or result.get("evidence_contract") != compact.CONTRACT_VERSION
                or not isinstance(result.get("entry_level_criteria"), dict)):
            raise ValueError("The two-argument builder requires an existing compact v2 payload")
    else:
        result = compact.build_payload(original_compact_payload, packet_or_criteria)
    source_hash = packet.get("resume_sources_sha256")
    if source_hash is not None and source_hash != _sha(result["resume_sources"]):
        raise ValueError("Fixed packet source fingerprint mismatch")
    assigned = result["evidence_scope"]["assigned_skill_ids"]
    selected = _packet_skills(packet, result["resume_sources"], assigned)
    activity_ids = {item["activity_id"] for item in selected.values()}
    result["resume_sources"] = [source for source in result["resume_sources"] if source["id"] in activity_ids]
    result["evidence_scope"]["activity_ids"] = [source["id"] for source in result["resume_sources"]]
    result["fixed_evidence_packets"] = {
        "version": PROTOCOL_VERSION,
        "selection_scope": SELECTION_SCOPE,
        "skills": selected,
    }
    return result


def audit_compliance(output, payload):
    """Audit scope adherence separately; this is not semantic or score validation."""
    assigned = payload["evidence_scope"]["assigned_skill_ids"]
    packets = _packet_skills(payload["fixed_evidence_packets"], payload["resume_sources"], assigned)
    body = output.get("result", {}) if isinstance(output, dict) else {}
    body = body if isinstance(body, dict) else {}
    raw_proofs = output.get("proofs", []) if isinstance(output, dict) else []
    raw_proofs = raw_proofs if isinstance(raw_proofs, list) else []
    pool, duplicate_ids = {}, set()
    for proof in raw_proofs:
        if not isinstance(proof, dict) or not isinstance(proof.get("proof_id"), str):
            continue
        pid = proof["proof_id"]
        if pid in pool:
            duplicate_ids.add(pid)
        else:
            pool[pid] = proof
    all_errors, records = [], []
    for skill in assigned:
        expected = packets[skill]
        allowed = set(expected["unit_ids"])
        anchors = set(expected["anchor_unit_ids"])
        record = body.get(skill)
        items = record.get("criteria") if isinstance(record, dict) else None
        skill_errors, criterion_audits = [], []
        expected_criteria = payload["entry_level_criteria"]["skills"][skill]["criteria"]
        expected_ids = [item["id"] for item in expected_criteria]
        if not isinstance(items, list):
            items = []
        if [item.get("criterion_id") if isinstance(item, dict) else None for item in items] != expected_ids:
            skill_errors.append("missing_duplicate_or_unordered_criteria")
        for item in items:
            if not isinstance(item, dict):
                continue
            criterion_id = item.get("criterion_id")
            status = item.get("status")
            refs = item.get("proof_ids")
            issues, referenced_units = [], []
            if not isinstance(refs, list):
                issues.append("invalid_reference_list")
                refs = []
            for pid in refs:
                if not isinstance(pid, str) or pid not in pool:
                    issues.append("unknown_proof_reference")
                    continue
                if pid in duplicate_ids:
                    issues.append("ambiguous_proof_reference")
                uid = pool[pid].get("unit_id")
                if not isinstance(uid, str) or uid not in allowed:
                    issues.append("proof_outside_skill_packet")
                if isinstance(uid, str):
                    referenced_units.append(uid)
            if (criterion_id == expected_ids[0] and status in {"supported", "partial", "uncertain"}
                    and not anchors.intersection(referenced_units)):
                issues.append("core_did_not_cite_fixed_anchor")
            criterion_audits.append({"criterion_id": criterion_id, "status": status,
                "referenced_unit_ids": referenced_units, "errors": sorted(set(issues))})
            skill_errors.extend(f"{criterion_id}:{issue}" for issue in sorted(set(issues)))
        records.append({"skill_id": skill, "fixed_activity_id": expected["activity_id"],
            "anchor_unit_ids": expected["anchor_unit_ids"], "compliant": not skill_errors,
            "criteria": criterion_audits, "errors": skill_errors})
        all_errors.extend({"skill_id": skill, "error": error} for error in skill_errors)
    return {"protocol_version": PROTOCOL_VERSION, "selection_scope": SELECTION_SCOPE,
        "compliant": not all_errors, "violating_skill_ids": [r["skill_id"] for r in records if not r["compliant"]],
        "errors": all_errors, "violations": all_errors, "skills": records, "scores_unchanged": True,
        "semantic_validation_performed": False,
        "scope_description": "Each skill is restricted to one complete original activity; positive or uncertain c1 must reference a fixed anchor. c2/c3 units and quote spans remain selectable inside that activity.",
        "limitation": "Fixes an activity and c1 anchor, not c2/c3 unit choice or quote spans. A cited anchor is not proof of semantic eligibility. Report raw scores and protocol adherence separately."}
