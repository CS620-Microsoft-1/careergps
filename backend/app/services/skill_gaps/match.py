"""Overall match: résumé evidence weighted by how often postings ask for each skill.

Uses the same demand weight as the skill priority ((required + preferred-only jobs) / N), so the
match and the gap ranking always agree. Skills that still need review stay out of both sides of the
ratio instead of counting as zero. This is an uncalibrated summary of the rubric, not a hiring
probability.
"""
from decimal import Decimal


def summarize_match(report: dict | None) -> dict | None:
    if not isinstance(report, dict) or not isinstance(report.get("skills"), list):
        return None
    earned = weight_total = Decimal(0)
    scored = 0
    for skill in report["skills"]:
        demand = skill.get("demand") or {}
        n = demand.get("N") or 0
        strength = skill.get("resume_evidence_strength")
        if n <= 0 or strength is None:
            continue
        weight = Decimal(demand.get("required_job_count", 0) + demand.get("preferred_only_job_count", 0)) / Decimal(n)
        if weight <= 0:
            continue
        scored += 1
        weight_total += weight
        earned += weight * Decimal(str(strength))
    if weight_total == 0:
        return None
    return {
        "score": float(round(earned / weight_total, 4)),
        "scored_skill_count": scored,
        "unscored_skill_count": sum(1 for skill in report["skills"] if skill.get("resume_evidence_strength") is None),
    }
