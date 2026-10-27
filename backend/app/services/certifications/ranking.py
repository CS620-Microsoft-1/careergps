"""Pick the gap skills worth covering and rank certifications without a model call."""
from app.schemas.certifications import Certification, CertificationRecommendation

MAX_GAPS = 8
MAX_RECOMMENDATIONS = 5


def top_gaps(report: dict, limit: int = MAX_GAPS) -> list[dict]:
    """Scored skills with a real gap, most urgent first. Unscored skills are never guessed."""
    gaps = [skill for skill in report["skills"]
            if skill.get("priority") is not None and (skill.get("skill_gap") or 0) > 0]
    gaps.sort(key=lambda skill: (-skill["priority"], skill["skill_id"]))
    return [{"skill_id": skill["skill_id"], "skill_name": skill["skill_name"],
             "skill_gap": skill["skill_gap"], "skill_gap_grade": skill["skill_gap_grade"],
             "priority": skill["priority"]} for skill in gaps[:limit]]


def rank(certifications: list[Certification], family: str, gaps: list[dict],
         limit: int = MAX_RECOMMENDATIONS) -> list[CertificationRecommendation]:
    """Greedy cover: each pick adds the most not-yet-covered gap priority, so picks don't repeat one skill."""
    priority = {gap["skill_id"]: gap["priority"] for gap in gaps}
    remaining = list(certifications)
    covered: set[str] = set()
    picks = []
    while remaining and len(picks) < limit:
        def gain(item: Certification) -> float:
            return sum(priority[skill] for skill in (set(item.skills[family]) & priority.keys()) - covered)
        best = max(remaining, key=lambda item: (gain(item), -remaining.index(item)))
        if gain(best) <= 0:
            break
        skill_ids = [skill for skill in best.skills[family] if skill in priority]
        picks.append(CertificationRecommendation(certification_id=best.id, skill_ids=skill_ids, reason=None))
        covered.update(skill_ids)
        remaining.remove(best)
    return picks
