"""Isolated, experimental entry-level contract; never imported by the runtime.

The model judges evidence against fixed criteria; this module performs reference
integrity checks and deterministic arithmetic, not semantic verification.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import re

from jsonschema import Draft202012Validator

from app.services.skill_gaps.schema import build_schema, choice, obj
from app.services.skill_gaps.skill_groups import GROUPS, GROUP_SKILLS, group_catalog
from app.services.skill_gaps.sources import build_index
from app.services.skill_gaps.validation import validate_response
from app.services.skill_gaps.scoring_math import grade

TASK = "assess_entry_level_readiness"
POLICY_VERSION = "entry-level-criterion-coverage.v1"
POLICY = {
    "policy_version": POLICY_VERSION,
    "calibration_status": "experimental_product_rubric_not_empirically_validated",
    "criterion_points": {"supported": 1.0, "partial": 0.5, "not_evidenced": 0.0},
    "critical_incomplete_cap": 0.6,
    "uncertainty_policy": "any_uncertain_or_invalid_scoring_criterion_leaves_skill_pending",
    "bonus_policy": "all_supplied_criteria_are_required_no_bonus_items",
    "market_policy": "unchanged_all_seniority_demand_weights",
}
REASONS = (
    "meets_criterion", "limited_scope", "missing_detail", "missing_evidence",
    "ambiguous_ownership", "ambiguous_capability", "conflicting_evidence", "unclear_meaning",
)


def _cards(catalog, group, family):
    return [dict(skill, module_id=module["module_id"], module_name=module["module_name"])
            for module in group_catalog(catalog, group)["families"][family]["modules"]
            for skill in module["skills"]]


def _criteria(criteria, family, skill):
    items = criteria["families"][family][skill]["criteria"]
    ids = [item["id"] for item in items]
    if not items or len(set(ids)) != len(ids):
        raise ValueError("Each skill needs unique nonempty criterion IDs")
    if any(not isinstance(item.get("weight"), (float, int)) or isinstance(item["weight"], bool)
           or item["weight"] <= 0 for item in items):
        raise ValueError("Each criterion needs a positive fixed weight")
    if any(item.get("minimum_evidence") not in {"knowledge", "practice"}
           or not isinstance(item.get("critical"), bool) for item in items):
        raise ValueError("Each criterion needs minimum evidence and a critical flag")
    return items


def build_format(catalog, group, criteria):
    """Retain original evidence definitions inside a new strict group contract."""
    if group not in GROUPS:
        raise ValueError("Unknown skill group")
    original = build_schema(group_catalog(catalog, group))["schema"]
    definitions = deepcopy(original["$defs"])
    branches = []
    for family in catalog["families"]:
        family_name = "Entry" + "".join(word.title() for word in family.split("_"))
        properties = {"job_family": choice(family)}
        for skill in _cards(catalog, group, family):
            skill_id = skill["skill_id"]
            items = _criteria(criteria, family, skill_id)
            name = family_name + "_" + skill_id
            criterion = obj({
                "criterion_id": choice(*(item["id"] for item in items)),
                "status": choice("supported", "partial", "not_evidenced", "uncertain"),
                "proofs": {"type": "array", "items": {"$ref": "#/$defs/Proof"}, "maxItems": 2},
                "reason_code": choice(*REASONS),
            })
            definitions[name] = obj({
                "evidence": {"$ref": "#/$defs/CoreEvidence"},
                "entry_level_assessment": obj({"criteria": {
                    "type": "array", "items": criterion,
                    "minItems": len(items), "maxItems": len(items),
                }}),
            })
            properties[skill_id] = {"$ref": "#/$defs/" + name}
        definitions[family_name] = obj(properties)
        branches.append({"$ref": "#/$defs/" + family_name})
    schema = obj({"task": choice(TASK), "result": {"anyOf": branches}})
    schema["$defs"] = definitions
    return {"name": f"careergps_entry_level_{group}_v1", "strict": True, "schema": schema}


def build_instructions(base_instructions, group):
    """Replace conflicting task/output prose; preserve the v12 factual policy."""
    if group not in GROUPS or f"branch must be {group}" not in base_instructions:
        raise ValueError("Original instructions must match the selected group")
    if "\nTASK\n" not in base_instructions or "\nOUTPUT\n" not in base_instructions:
        raise ValueError("Unexpected original instruction structure")
    body = base_instructions.split("\nOUTPUT\n", 1)[0]
    body = body.replace("skill-group evidence extractor", "skill-group evidence extractor and entry-level assessor", 1)
    body = body.replace("Run extract_resume_evidence from resume_sources and selected core_skills.",
                        "Run assess_entry_level_readiness from resume_sources, selected core_skills, and entry_level_criteria. First extract factual evidence using the original rules below; independently assess the supplied entry-level criteria.")
    return body + """

ENTRY-LEVEL READINESS
Assess demonstrated readiness for new-graduate and entry-level work against the supplied, versioned entry_level_criteria for each assigned skill. These are explicit experimental product criteria, not inferred job-market statistics. Do not invent, modify, omit, or add requirements. Market demand is computed separately by Python and must not influence evidence labels.
Preserve the original evidence classification and all source, ownership, negation, exact-quote and same-operation rules. Do not relabel knowledge as practice, or invent methods, checks or results to improve readiness. A high entry-level grade is not a goal.
Coursework, personal projects, research, internships and employment are eligible when the applicant's relevant contribution is explicit. Do not require production scale, business impact, architectural ownership or numeric improvements unless the supplied criterion explicitly requires them. Missing advanced evidence does not itself fail a criterion; missing evidence required by that criterion still does.
Each skill has fixed criteria with IDs, descriptions, minimum_evidence, critical flags and weights. All supplied criteria are required for this pilot; no bonus items offset missing requirements. Weights and caps are used only by Python. Respect the full criterion and any stated alternative; do not demand every example in an 'or' list.
For each criterion return exactly one status:
- supported: eligible evidence supports the complete criterion.
- partial: eligible evidence supports an identifiable part but a required detail is missing. The minimum evidence type must still be met.
- not_evidenced: after examining all supplied sources, no eligible supporting evidence was found. This does not mean the applicant lacks the ability. Return proofs:[] and reason_code:missing_evidence.
- uncertain: relevant evidence is genuinely ambiguous in meaning, ownership or applicability. Retain uncertainty; do not replace it with partial, knowledge or absence to obtain a number.
For supported or partial, cite one or two shortest sufficient exact contiguous original proofs. minimum_evidence:practice requires claim units showing the applicant's actual operation; a listed skill or course title cannot meet it. minimum_evidence:knowledge allows claim or listed units only to the extent they support the specific criterion: a bare skill name does not establish concepts, steps or explanation not stated. Never infer proficiency from titles, years, degrees, tool implementation languages or team outcomes.
Criterion references may cite other relevant activities than the single preferred original evidence record. Assess independent criteria separately, but never combine different activities into one claimed operation, method, check or result. If a criterion links an operation to a method/check, all its proofs must concern the same activity and capability. No unrelated result may support a criterion. Preserve uncertainty if a relevant connection cannot be established.
Consistency: if a practice criterion has positive support, the original core evidence must also establish eligible practice or limited_practice; do not report core evidence as knowledge/absent while claiming practical criterion support. If original core evidence is uncertain, do not claim a resolved entry-level grade.
Use a concise reason_code from the schema. Do not output prose explanations or numerical scores. No tools, browsing, repair call or second response.

OUTPUT
Return only the approved entry-level group Schema: task:assess_entry_level_readiness, result.job_family, and exactly the assigned skill keys. Each skill contains evidence (the unchanged original v12 evidence record) and entry_level_assessment.criteria. Return all supplied criterion IDs exactly once in their supplied order. Omit every unassigned skill.
Do not return grades, skill gaps, summaries or recommendations. Python independently validates references, retains the original evidence score, computes criterion coverage with the fixed policy, and applies unchanged all-job demand weights. Recheck original evidence rules, every criterion ID/status/proof, source kind, ownership and exact quotes before returning one final response.
"""


def build_payload(base_group_payload, criteria):
    payload = deepcopy(base_group_payload)
    family = payload["job_family"]
    group = payload["evidence_scope"]["branch"]
    ids = payload["evidence_scope"]["assigned_skill_ids"]
    if set(ids) != set(GROUP_SKILLS[family][group]):
        raise ValueError("Entry-level input must preserve the existing group partition")
    payload["task"] = TASK
    payload["entry_level_criteria"] = {
        "version": criteria["version"],
        "target_levels": criteria.get("target_levels", ["new_grad", "entry_level"]),
        "calibration": criteria.get("calibration", POLICY["calibration_status"]),
        "skills": {skill: {"criteria": deepcopy(_criteria(criteria, family, skill))} for skill in ids},
    }
    return payload


def unpack_output(output):
    """Losslessly project model evidence back to the existing v12 validator."""
    body = output.get("result") if isinstance(output, dict) else None
    if not isinstance(body, dict):
        return {"task": "extract_resume_evidence", "result": {}}
    result = {"job_family": body.get("job_family")}
    for skill, record in body.items():
        if skill != "job_family":
            result[skill] = deepcopy(record.get("evidence")) if isinstance(record, dict) else None
    return {"task": "extract_resume_evidence", "result": result}


def assess_output(output, payload, catalog, criteria):
    """Validate all prerequisites, then compute coverage without model repair."""
    family, group = payload["job_family"], payload["evidence_scope"]["branch"]
    expected_payload = build_payload({k: deepcopy(v) for k, v in payload.items()
                                      if k != "entry_level_criteria"}, criteria)
    if payload != expected_payload:
        raise ValueError("Supplied criterion payload differs from the frozen criteria")
    format_ = build_format(catalog, group, criteria)
    schema_errors = [{"path": "/" + "/".join(map(str, e.path)), "validator": e.validator}
                     for e in Draft202012Validator(format_["schema"]).iter_errors(output)]
    index = build_index(payload["resume_sources"])
    evidence = unpack_output(output)
    evidence_checks = validate_response(evidence, family, payload["resume_sources"], group_catalog(catalog, group))
    body = output.get("result", {}) if isinstance(output, dict) else {}
    if not isinstance(body, dict):
        body = {}
    report = {"policy_version": POLICY_VERSION, "calibration_status": POLICY["calibration_status"],
              "job_family": family, "branch": group, "criteria_version": criteria["version"],
              "skills": [], "unscored_skill_ids": [],
              "validation": {"schema_errors": schema_errors, "original_evidence_checks": evidence_checks,
                             "semantic_validation_performed": False, "exact_proof_integrity_checked": True}}
    for card in _cards(catalog, group, family):
        skill = card["skill_id"]
        required = _criteria(criteria, family, skill)
        record = body.get(skill)
        record = record if isinstance(record, dict) else {}
        original = record.get("evidence")
        original = original if isinstance(original, dict) else {}
        assessment = record.get("entry_level_assessment")
        assessment = assessment if isinstance(assessment, dict) else {}
        observed = assessment.get("criteria")
        observed = observed if isinstance(observed, list) else []
        errors = []
        if schema_errors:
            errors.append("entry_schema_invalid")
        if evidence_checks["global_errors"] or evidence_checks["skills"][skill]["status"] != "passed":
            errors.append("original_evidence_invalid")
        if original.get("kind") == "uncertain":
            errors.append("original_evidence_uncertain")
        if [r.get("criterion_id") if isinstance(r, dict) else None for r in observed] != [c["id"] for c in required]:
            errors.append("criterion_ids_missing_duplicate_or_out_of_order")
        observed_by_id = {r.get("criterion_id"): r for r in observed if isinstance(r, dict)}
        audits, weighted, total = [], Decimal(0), Decimal(0)
        cap = False
        for criterion in required:
            item = observed_by_id.get(criterion["id"], {})
            status = item.get("status")
            proofs = item.get("proofs")
            proofs = proofs if isinstance(proofs, list) else []
            issues = []
            positive = status in {"supported", "partial"}
            if status == "uncertain":
                issues.append("criterion_uncertain")
            elif status not in POLICY["criterion_points"]:
                issues.append("criterion_status_invalid")
            if positive and not proofs:
                issues.append("positive_criterion_without_proof")
            if status == "not_evidenced" and proofs:
                issues.append("not_evidenced_has_positive_proofs")
            if len(proofs) > 2:
                issues.append("too_many_proofs")
            if positive and original.get("kind") == "absent":
                issues.append("positive_criterion_contradicts_absent_core")
            if positive and criterion["minimum_evidence"] == "practice":
                if original.get("kind") not in {"practice", "limited_practice"}:
                    issues.append("practice_criterion_without_practice_core")
                elif original.get("capability", {}).get("relation") != "direct_personal":
                    issues.append("practice_core_not_direct_personal")
            proof_audits = []
            for proof in proofs:
                if not isinstance(proof, dict):
                    issues.append("invalid_proof")
                    continue
                unit = index.get(proof.get("unit_id"))
                quote = proof.get("quote")
                if unit is None:
                    issues.append("unknown_proof_unit")
                    continue
                if not isinstance(quote, str) or not quote.strip() or quote not in unit["text"]:
                    issues.append("quote_not_exact")
                    continue
                allowed = {"claim"} if positive and criterion["minimum_evidence"] == "practice" else {"claim", "listed"}
                if unit["kind"] not in allowed:
                    issues.append("ineligible_proof_kind")
                proof_audits.append({"unit_id": unit["id"], "activity_id": unit["activity_id"],
                                     "kind": unit["kind"], "quote": quote, "start": unit["text"].find(quote)})
            # A criterion describes one capability assertion, so its supporting
            # operation and detail/check cannot be spliced across activities.
            if positive and criterion["minimum_evidence"] == "practice" and len({p["activity_id"] for p in proof_audits}) > 1:
                issues.append("cross_activity_practice_criterion")
            point = POLICY["criterion_points"].get(status)
            weight = Decimal(str(criterion["weight"]))
            total += weight
            if point is not None:
                weighted += weight * Decimal(str(point))
            if criterion["critical"] and status != "supported":
                cap = True
            audits.append({"criterion_id": criterion["id"], "status": status, "weight": float(weight),
                           "critical": criterion["critical"], "points": point, "proofs": proof_audits,
                           "errors": issues, "reason_code": item.get("reason_code")})
            errors.extend(f"{criterion['id']}:{issue}" for issue in issues)
        score = None if errors else weighted / total
        cap_applied = score is not None and cap and score > Decimal(str(POLICY["critical_incomplete_cap"]))
        if cap_applied:
            score = Decimal(str(POLICY["critical_incomplete_cap"]))
        gap = None if score is None else Decimal(1) - score
        row = {"skill_id": skill, "skill_name": card["skill_name"], "module_id": card["module_id"],
               "module_name": card["module_name"], "entry_level_score": None if score is None else round(float(score), 6),
               "entry_level_gap": None if gap is None else round(float(gap), 6),
               "entry_level_grade": grade(None if gap is None else float(gap)),
               "calculation_state": "needs_confirmation" if score is None else "scored",
               "critical_cap_applied": cap_applied, "criterion_audits": audits, "errors": errors}
        report["skills"].append(row)
        if score is None:
            report["unscored_skill_ids"].append(skill)
    return report
