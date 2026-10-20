"""Deterministic local calculations. This module never imports database code."""
import json

from app.schemas.skill_gap import (
    AgentInput, CalculatedGap, CandidateSkill, ConfirmedResume, MarketContext,
    MarketInput, SkillGapResult,
)

ALIASES = {
    "js": "JavaScript", "javascript": "JavaScript", "ecmascript": "JavaScript",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "react": "React", "react.js": "React", "reactjs": "React",
    "python": "Python", "docker": "Docker", "git": "Git", "sql": "SQL",
}


def normalize_skill(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("Skill names cannot be blank.")
    return ALIASES.get(cleaned.casefold(), cleaned)


def priority(score: float) -> str:
    return "high" if score >= 0.6 else "medium" if score >= 0.3 else "low"


def calculate_gaps(resume: ConfirmedResume, market: MarketInput) -> AgentInput:
    candidates: dict[str, CandidateSkill] = {}
    for item in resume.candidate_skills:
        name = normalize_skill(item.skill)
        key = name.casefold()
        if key in candidates:
            existing = candidates[key]
            # Multiple mentions never sum to a fictitious proficiency level.
            existing.evidence_score = max(existing.evidence_score, item.evidence_score)
            existing.evidence = list(dict.fromkeys(existing.evidence + item.evidence))
        else:
            candidates[key] = item.model_copy(update={"skill": name, "evidence": list(item.evidence)})

    gaps = []
    seen = set()
    for item in market.skills:
        name = normalize_skill(item.skill)
        key = name.casefold()
        if key in seen:
            raise ValueError(f"Duplicate market skill after normalization: {name}")
        seen.add(key)
        candidate = candidates.get(key)
        score = candidate.evidence_score if candidate else 0.0
        gaps.append(CalculatedGap(
            skill=name, market_frequency=item.frequency, user_evidence_score=score,
            gap_score=round(item.frequency * (1 - score), 6),
            market_examples=item.examples, user_evidence=candidate.evidence if candidate else [],
        ))
    gaps.sort(key=lambda item: (-item.gap_score, item.skill.casefold()))
    return AgentInput(
        target_role=market.target_role, seniority=market.seniority,
        market=MarketContext(
            window_days=market.window_days, sample_size=market.sample_size,
            company_count=market.company_count,
            low_confidence=(market.low_confidence or market.sample_size < 30
                            or market.company_count < 3 or not market.skills),
        ),
        candidate_skills=list(candidates.values()), calculated_gaps=gaps,
    )


def validate_agent_result(raw: str, inputs: AgentInput) -> SkillGapResult:
    """Reject numeric tampering, invented skills, missing rows, and reordered gaps."""
    result = SkillGapResult.model_validate_json(raw)
    if (result.target_role, result.seniority) != (inputs.target_role, inputs.seniority):
        raise ValueError("Agent changed the target role or seniority.")
    expected_confidence = "low" if inputs.market.low_confidence else "high"
    if result.confidence != expected_confidence:
        raise ValueError("Agent changed the prescribed sample confidence.")
    if inputs.market.low_confidence and not result.limitations:
        raise ValueError("Low-confidence results must describe their limitations.")
    if [gap.skill for gap in result.gaps] != [gap.skill for gap in inputs.calculated_gaps]:
        raise ValueError("Agent changed the skill list or order.")
    for actual, expected in zip(result.gaps, inputs.calculated_gaps):
        for field in ("market_frequency", "user_evidence_score", "gap_score"):
            if getattr(actual, field) != getattr(expected, field):
                raise ValueError(f"Agent changed {field} for {expected.skill}.")
        if actual.priority != priority(expected.gap_score):
            raise ValueError(f"Agent changed the priority for {expected.skill}.")
    supported = {skill.skill for skill in inputs.candidate_skills if skill.evidence_score >= 0.6}
    strength_names = [item.skill for item in result.strengths]
    if len(set(strength_names)) != len(strength_names) or not set(strength_names) <= supported:
        raise ValueError("Agent returned an unsupported or duplicate strength.")
    return result


def mock_response(inputs: AgentInput) -> str:
    gaps = []
    for gap in inputs.calculated_gaps:
        evidence = ("not demonstrated" if gap.user_evidence_score == 0 else
                    "demonstrated" if gap.user_evidence_score == 1 else "partially demonstrated")
        action = (f"Maintain and document the supplied {gap.skill} evidence."
                  if gap.gap_score == 0 else
                  f"Add a small {gap.skill} feature to an existing project and "
                  "document its implementation and verification.")
        gaps.append({
            "skill": gap.skill, "market_frequency": gap.market_frequency,
            "user_evidence_score": gap.user_evidence_score, "gap_score": gap.gap_score,
            "priority": priority(gap.gap_score),
            "reason": f"{gap.skill} is {evidence} in the supplied résumé evidence; "
                      f"it appears in {gap.market_frequency:.0%} of the synthetic market sample.",
            "recommended_action": action,
            "completion_evidence": "A repository change, a reproducible demonstration, "
                                   "and a résumé bullet describing the work actually completed.",
        })
    return json.dumps({
        "target_role": inputs.target_role, "seniority": inputs.seniority,
        "confidence": "low" if inputs.market.low_confidence else "high",
        "summary": ("Mock output for pipeline validation; all inputs and recommendations are synthetic."
                    if inputs.calculated_gaps else
                    "No market skills were supplied; a skill-gap comparison cannot be made."),
        "strengths": [
            {"skill": item.skill, "explanation": "; ".join(item.evidence)}
            for item in inputs.candidate_skills if item.evidence_score >= 0.6
        ],
        "gaps": gaps,
        "limitations": ["Synthetic fixture data; scores are experimental evidence heuristics."]
                       + (["Limited market sample."] if inputs.market.low_confidence else []),
    }, ensure_ascii=False)
