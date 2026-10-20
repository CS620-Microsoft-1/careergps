"""File-based prototype contracts; scores are heuristics, not verified proficiency."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CandidateSkill(StrictModel):
    skill: str = Field(min_length=1)
    evidence_score: float = Field(ge=0, le=1)
    evidence: list[str]

    @model_validator(mode="after")
    def require_supporting_evidence(self):
        if self.evidence_score > 0 and not any(line.strip() for line in self.evidence):
            raise ValueError("A positive evidence score needs supporting résumé evidence.")
        return self


class ConfirmedResume(StrictModel):
    confirmed: Literal[True]
    candidate_skills: list[CandidateSkill]


class MarketSkill(StrictModel):
    skill: str = Field(min_length=1)
    frequency: float = Field(ge=0, le=1)
    examples: list[str] = Field(default_factory=list)


class MarketInput(StrictModel):
    target_role: str = Field(min_length=1)
    seniority: Literal["intern", "entry", "mid", "senior"]
    window_days: int = Field(gt=0)
    sample_size: int = Field(ge=0)
    company_count: int = Field(ge=0)
    low_confidence: bool
    skills: list[MarketSkill]

    @model_validator(mode="after")
    def check_sample(self):
        if self.company_count > self.sample_size:
            raise ValueError("company_count cannot exceed sample_size.")
        if self.sample_size == 0 and any(skill.frequency > 0 for skill in self.skills):
            raise ValueError("Positive skill frequencies need a nonempty market sample.")
        return self


class MarketContext(StrictModel):
    window_days: int
    sample_size: int
    company_count: int
    low_confidence: bool


class CalculatedGap(StrictModel):
    skill: str
    market_frequency: float = Field(ge=0, le=1)
    user_evidence_score: float = Field(ge=0, le=1)
    gap_score: float = Field(ge=0, le=1)
    market_examples: list[str]
    user_evidence: list[str]


class AgentInput(StrictModel):
    target_role: str
    seniority: str
    market: MarketContext
    candidate_skills: list[CandidateSkill]
    calculated_gaps: list[CalculatedGap]


class Strength(StrictModel):
    skill: str
    explanation: str = Field(min_length=1)


class ExplainedGap(StrictModel):
    skill: str
    market_frequency: float = Field(ge=0, le=1)
    user_evidence_score: float = Field(ge=0, le=1)
    gap_score: float = Field(ge=0, le=1)
    priority: Literal["high", "medium", "low"]
    reason: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    completion_evidence: str = Field(min_length=1)


class SkillGapResult(StrictModel):
    target_role: str
    seniority: str
    confidence: Literal["high", "low"]
    summary: str = Field(min_length=1)
    strengths: list[Strength]
    gaps: list[ExplainedGap]
    limitations: list[str]
