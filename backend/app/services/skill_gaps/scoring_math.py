"""Trust Agent categories; apply a semantic eligibility gate and fixed arithmetic.

No source/quote/ID checking, generated-result Schema validation, or repair occurs.
Unknown arithmetic inputs stay unscored instead of becoming zero.
"""
from decimal import Decimal
import json
from .assets import ASSET_ROOT

POLICY = json.loads((ASSET_ROOT / "scoring_policy.json").read_text(encoding="utf-8"))
POLICY_VERSION = POLICY["policy_version"]


def grade(gap):
    if gap is None:
        return None
    value = Decimal(str(gap))
    for ceiling, label in [("0.1", "A"), ("0.2", "A-"), ("0.3", "B+"),
                           ("0.4", "B"), ("0.6", "C")]:
        if value <= Decimal(ceiling):
            return label
    return "D" if value < 1 else "F"


def score_item(item):
    if not isinstance(item, dict):
        return {"state": "unscored", "score": None, "reason": "unavailable_item"}
    relation = item.get("support_relation")
    if not isinstance(relation, str):
        return {"state": "unscored", "score": None, "reason": "unavailable_support_relation"}
    if relation in {"indirect", "none"}:
        return {"state": "excluded", "score": 0.0, "reason": "not_direct_support"}
    if relation != "direct":
        return {"state": "unscored", "score": None, "reason": "uncertain_support"}
    owner = item.get("attribution")
    if not isinstance(owner, str):
        return {"state": "unscored", "score": None, "reason": "unavailable_attribution"}
    if owner == "other":
        return {"state": "excluded", "score": 0.0, "reason": "another_person_activity"}
    application = item.get("application_detail")
    if owner not in {"self", "not_applicable"}:
        return {"state": "unscored", "score": None, "reason": "uncertain_attribution"}
    if application == "listed":
        return {"state": "scored", "score": POLICY["listed_score"],
                "reason": "direct_knowledge_claim_only", "points": None, "caps_applied": ["listed_score"]}
    if owner != "self":
        return {"state": "unscored", "score": None, "reason": "practice_not_attributed_to_applicant"}
    # Map categorical features to a rubric, not to any keyword or candidate.
    categories = {"application": application, "method": item.get("method_detail"),
                  "validation": item.get("validation_level")}
    points = {}
    for axis, category in categories.items():
        mapping = POLICY[axis + "_points"]
        if not isinstance(category, str) or category not in mapping:
            return {"state": "unscored", "score": None, "reason": "unavailable_rubric_category"}
        points[axis] = mapping[category]
    total = sum(points.values())
    score = Decimal(total) / Decimal(POLICY["points_denominator"])
    caps = []
    if application == "task_only" and score > Decimal(str(POLICY["task_only_cap"])):
        score = Decimal(str(POLICY["task_only_cap"]))
        caps.append("task_only_cap")
    return {"state": "scored", "score": float(score), "reason": "direct_personal_practice",
            "categories": categories, "points": points, "total_points": total,
            "points_denominator": POLICY["points_denominator"], "caps_applied": caps}


def assess_strength(assessment):
    if not isinstance(assessment, dict):
        return {"score": None, "state": "unscored", "reason": "unavailable_assessment"}
    status = assessment.get("status")
    if not isinstance(status, str):
        return {"score": None, "state": "unscored", "reason": "unavailable_status"}
    if status == "not_evidenced":
        return {"score": 0.0, "state": "scored", "reason": "no_positive_resume_evidence"}
    if status not in {"supported", "partial"}:
        return {"score": None, "state": "unscored", "reason": "needs_confirmation"}
    evidence = assessment.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return {"score": None, "state": "unscored", "reason": "unavailable_evidence"}
    items = [score_item(item) for item in evidence]
    usable = [(i, item) for i, item in enumerate(items) if item["state"] == "scored"]
    if not usable:
        pending = any(item["state"] == "unscored" for item in items)
        return {"score": None if pending else 0.0, "state": "unscored" if pending else "scored",
                "reason": "no_complete_direct_item" if pending else "no_direct_personal_evidence",
                "item_results": items}
    selected_index, selected = max(usable, key=lambda pair: pair[1]["score"])
    result = {**selected, "selected_evidence_index": selected_index, "item_results": items,
              "has_unscored_items": any(item["state"] == "unscored" for item in items)}
    if status == "partial" and result["score"] > POLICY["partial_cap"]:
        result["score"] = POLICY["partial_cap"]
        result["caps_applied"] = [*result.get("caps_applied", []), "partial_cap"]
    return result


def evidence_strength(assessment):
    return assess_strength(assessment)["score"]


def calculate(family, agent_output, catalog, market):
    family_catalog = catalog["families"][family]
    demand = market["families"][family]
    result = agent_output.get("result") if isinstance(agent_output, dict) else None
    skills = result.get("skills") if isinstance(result, dict) else None
    skills = skills if isinstance(skills, dict) else {}
    n = demand["total_job_count"]
    rows = []
    for module in family_catalog["modules"]:
        for skill in module["skills"]:
            key = skill["skill_id"]
            assessment = skills.get(key)
            breakdown = assess_strength(assessment)
            score = breakdown["score"]
            counts = demand["skills"][key]
            weight = (Decimal(counts["required_job_count"]) +
                      Decimal(counts["preferred_only_job_count"])) / Decimal(n)
            gap = None if score is None else Decimal(1) - Decimal(str(score))
            rows.append({
                "skill_id": key, "skill_name": skill["skill_name"],
                "module_id": module["module_id"], "module_name": module["module_name"],
                "agent_assessment": assessment, "evidence_verification": "not_performed",
                "resume_evidence_strength": score, "scoring_breakdown": breakdown,
                "skill_gap": None if gap is None else float(gap), "skill_gap_grade": grade(gap),
                "demand": {**counts, "N": n}, "demand_weight": round(float(weight), 6),
                "priority": None if gap is None else round(float(weight * gap), 6),
                "calculation_state": "needs_confirmation" if score is None else "scored",
            })
    ranked = sorted((r for r in rows if r["priority"] is not None and r["skill_gap"] > 0),
                    key=lambda row: (-row["priority"], row["skill_id"]))
    return {
        "policy_version": POLICY_VERSION, "calibration_status": POLICY["calibration_status"],
        "job_family": family, "metric": "core-skill resume evidence strength and evidence gap",
        "agent_output_verified": False, "database_used": False,
        "core_skill_count": len(rows), "module_count": len(family_catalog["modules"]),
        "demand_snapshot_fingerprint": market["source_fingerprint"],
        "skills": rows, "priority_order": [r["skill_id"] for r in ranked],
        "unscored_skill_ids": [r["skill_id"] for r in rows if r["priority"] is None],
        "limitations": [
            "Agent support relations and categories are trusted without source verification or repair.",
            "The initial rubric has not been empirically calibrated; this is not an ability or probability estimate.",
            "Each evidence item is scored separately; the strongest complete direct item wins without a quantity bonus.",
            "Core evidence is not complete coverage of every specific job requirement.",
            "A means a smaller evidence gap; F means no positive resume evidence, not inability.",
            "Demand affects priority, not the gap grade; unspecified demand is reported separately.",
            "The v5 rubric is not numerically interchangeable with historical v4 scores.",
        ],
    }
