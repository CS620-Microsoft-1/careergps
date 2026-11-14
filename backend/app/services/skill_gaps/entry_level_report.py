"""Expose verified entry-level scores through the existing Skill Gap report."""

from copy import deepcopy
from decimal import Decimal

from .entry_level import verified_proofs
from .skill_groups import GROUPS, GROUP_SKILLS
from .sources import build_index


POLICY_VERSION = "entry-level-evidence.v1"
RESPONSE_PROCESSING_VERSION = "entry-level-exact-citation-review.v1"
_PROOF_FIELDS = {"c1": "capability/quote", "c2": "method/proof/quote", "c3": "validation/check/quote"}
_CREDITED = {"supported", "partial"}
_CHECK_SCOPE = "fixed_candidate_and_original_quote_integrity"


def _validated_rows(family, assessments):
    if set(assessments) != set(GROUPS):
        raise ValueError("A verified assessment is required for every skill group")
    by_skill = {}
    for group in GROUPS:
        assessment = assessments[group]
        rows = {row["skill_id"]: row for row in assessment["skills"]}
        if ((assessment["job_family"], assessment["branch"]) != (family, group)
                or len(rows) != len(assessment["skills"])
                or rows.keys() != set(GROUP_SKILLS[family][group])
                or assessment["citation_review"]["group_blocking_errors"]):
            raise ValueError("A skill group failed scope or evidence validation")
        by_skill.update(rows)
    return by_skill


def _proofs_by_criterion(row, index):
    credited = {(proof["unit_id"], proof["quote"]) for proof in verified_proofs(row)}
    selected = {}
    for criterion in row["criterion_audits"]:
        if criterion["status"] not in _CREDITED or not criterion["points"]:
            continue
        by_span = {}
        for proof in criterion["proofs"]:
            uid, quote = proof["unit_id"], proof["quote"]
            if (uid, quote) not in credited:
                continue
            unit = index.get(uid)
            if unit is None or not quote.strip() or quote not in unit["text"]:
                raise ValueError("A verified proof no longer matches its original source")
            by_span[uid, quote] = {"unit_id": uid, "quote": quote}
        if by_span:
            selected[criterion["criterion_id"]] = list(by_span.values())
    return selected


def _display_assessment(row, proofs):
    score = row["entry_level_score"]
    if score is None:
        reason = row.get("selection_review", {}).get("reason")
        explanation = {
            "candidate_selection_incomplete": "Relevant evidence may be missing from the passages that could be scored.",
            "cross_activity_practice_evidence": "The cited passages need to be checked for a shared project.",
        }.get(reason, "The cited evidence for this skill needs review before it can be scored.")
        return {"kind": "uncertain", "reason": explanation}
    if score == 0:
        return {"kind": "absent"}
    if not proofs:
        raise ValueError("A positive score requires a verified proof")
    core = next(iter(proofs.values()))[0]
    core_criterion = row["criterion_audits"][0]
    if "c1" not in proofs or core_criterion["basis"] != "practice":
        return {"kind": "knowledge", "evidence_id": core["unit_id"]}
    method = proofs.get("c2", [])
    support = proofs.get("c3", [])
    return {
        "kind": "limited_practice" if core_criterion["status"] == "partial" else "practice",
        "operation_id": core["unit_id"],
        "capability": {"relation": "direct_personal", "quote": core["quote"]},
        "method": {"kind": "criterion_evidence", "proof": method[0]} if method else None,
        "validation": {"kind": "criterion_evidence", "check": support[0], "finding": None,
                       "reference": None, "finding_type": None, "reported_value": None,
                       "relation": "same_capability"} if support else None,
    }


def _reference_check(row, proofs, index):
    sid = row["skill_id"]
    spans = []
    for criterion, items in proofs.items():
        for proof in items:
            uid, quote = proof["unit_id"], proof["quote"]
            start = index[uid]["text"].index(quote)
            spans.append({"field": f"/result/{sid}/{_PROOF_FIELDS[criterion]}",
                          "unit_id": uid, "start": start, "end": start + len(quote)})
    ids = list(dict.fromkeys(span["unit_id"] for span in spans))
    activities = {index[uid]["activity_id"] for uid in ids}
    errors = list(row["errors"])
    if row.get("selection_review"):
        errors.append(row["selection_review"]["reason"])
    return {
        "status": "needs_confirmation" if row["entry_level_score"] is None else "passed",
        "errors": [{"code": error.split(":")[-1], "field": f"/result/{sid}",
                    "detail": error.replace(":", " ").replace("_", " ").capitalize()}
                   for error in dict.fromkeys(errors)],
        "evidence_ids": ids,
        "derived_activity_id": next(iter(activities)) if len(activities) == 1 else None,
        "activity_derivation": "original_credited_proof_units" if len(activities) == 1 else None,
        "proof_spans": spans,
        "reported_value_spans": [],
    }


def _report_row(verified, skill, module, demand, n, index):
    score = verified["entry_level_score"]
    if verified["calculation_state"] != ("needs_confirmation" if score is None else "scored"):
        raise ValueError("A verified skill score and its calculation state disagree")
    gap = None if score is None else Decimal(1) - Decimal(str(score))
    weight = Decimal(demand["required_job_count"] + demand["preferred_only_job_count"]) / Decimal(n)
    proofs = _proofs_by_criterion(verified, index) if score else {}
    return {
        "skill_id": skill["skill_id"], "skill_name": skill["skill_name"],
        "module_id": module["module_id"], "module_name": module["module_name"],
        "resume_evidence_strength": score, "skill_gap": None if gap is None else float(gap),
        "skill_gap_grade": verified["entry_level_grade"],
        "priority": None if gap is None else round(float(weight * gap), 6),
        "demand_weight": round(float(weight), 6), "demand": {**demand, "N": n},
        "calculation_state": verified["calculation_state"],
        "agent_assessment": _display_assessment(verified, proofs),
        "evidence_verification": _CHECK_SCOPE,
        "local_reference_check": _reference_check(verified, proofs, index),
        "scoring_breakdown": {
            "score": score, "state": verified["calculation_state"],
            "criteria": [{**{key: criterion[key] for key in ("criterion_id", "status", "basis", "weight", "points")},
                          "proofs": proofs.get(criterion["criterion_id"], [])}
                         for criterion in verified["criterion_audits"]],
            "critical_cap_applied": verified["critical_cap_applied"],
            "partial_core_applied": verified.get("partial_core_applied", False),
        },
    }


def score_demand_coverage(report):
    """Share of all-job demand accounted for by scored skills in the report."""
    total = covered = 0
    for row in report["skills"]:
        demand = row["demand"]
        count = demand["required_job_count"] + demand["preferred_only_job_count"]
        total += count
        if row["resume_evidence_strength"] is not None:
            covered += count
    return covered / total if total else None


def build_report(family, assessments, catalog, market, sources):
    """Project assessed rows into the public and persisted report shapes."""
    verified = _validated_rows(family, assessments)
    modules = catalog["families"][family]["modules"]
    demand = market["families"][family]
    index = build_index(sources)
    activities = {source["id"]: source for source in sources}
    rows = [_report_row(verified[skill["skill_id"]], skill, module, demand["skills"][skill["skill_id"]],
                        demand["total_job_count"], index)
            for module in modules for skill in module["skills"]]
    if {row["skill_id"] for row in rows} != verified.keys():
        raise ValueError("The verified skills and public catalog disagree")
    ranked = sorted((row for row in rows if row["skill_gap"] is not None and row["skill_gap"] > 0),
                    key=lambda row: (-row["priority"], row["skill_id"]))
    pending = [row["skill_id"] for row in rows if row["resume_evidence_strength"] is None]
    cited = {uid for row in rows for uid in row["local_reference_check"]["evidence_ids"]}
    source_index = {}
    for uid in sorted(cited):
        unit = index[uid]
        source = activities[unit["activity_id"]]
        source_index[uid] = {**unit, "activity_path": source["path"], "activity_context": deepcopy(source["context"])}
    practice = [row for row in rows if row["agent_assessment"]["kind"] in {"practice", "limited_practice"}]
    report = {
        "policy_version": POLICY_VERSION, "base_numeric_rubric": POLICY_VERSION,
        "calibration_status": "uncalibrated", "job_family": family,
        "metric": "entry-level resume evidence strength and evidence gap",
        "core_skill_count": len(rows), "module_count": len(modules),
        "demand_snapshot_fingerprint": market["source_fingerprint"],
        "skills": rows, "priority_order": [row["skill_id"] for row in ranked],
        "unscored_skill_ids": pending, "source_index": source_index,
        "reference_validation": {"status": "partial" if pending else "passed", "scope": _CHECK_SCOPE,
                                 "global_errors": [], "unexpected_skill_ids": [],
                                 "skills": {row["skill_id"]: row["local_reference_check"] for row in rows}},
        "evidence_coverage": {"scope": "credited_criterion_display",
                              "method_null_skill_ids": [row["skill_id"] for row in practice
                                                        if row["agent_assessment"]["method"] is None],
                              "validation_null_skill_ids": [row["skill_id"] for row in practice
                                                            if row["agent_assessment"]["validation"] is None],
                              "candidate_references": {}},
        "mechanical_integrity_checked": True, "exact_quotes_checked": True, "semantic_evidence_verified": False,
        "agent_output_verified": False, "database_used": False, "unresolved_display_sources": [],
        "source_lookup_scope": "credited_original_criterion_proofs",
        "response_processing": {"version": RESPONSE_PROCESSING_VERSION,
                                "scope": "projection_of_validated_criterion_results",
                                "count": 0, "adjustments": []},
        "limitations": [
            "Citations are checked for exact source text and criterion permission. The Agent judges their meaning.",
            "Demand covers all levels of the selected occupation and weights the overall match and gap priority.",
        ],
    }
    coverage = score_demand_coverage(report)
    if pending and coverage is not None:
        report["limitations"].append(
            f"{len(pending)} skills need confirmation. Scored skills cover {coverage:.1%} of the demand weight."
        )
    return report
