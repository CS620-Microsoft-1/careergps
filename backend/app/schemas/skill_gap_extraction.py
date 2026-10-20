"""Raw-input contracts reuse the current Review UI and job-board contracts."""
from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.market import NormalizedPosting, Seniority
from app.schemas.resume import ResumeClassification
from app.schemas.skill_gap import StrictModel


class ReviewedResume(StrictModel):
    confirmed: Literal[True]
    classification: ResumeClassification


class PostingDocument(StrictModel):
    company_name: str = Field(min_length=1)
    posting: NormalizedPosting

    @property
    def posting_id(self) -> str:
        return f"{self.posting.source}:{self.posting.external_id}"


class PostingSnapshot(StrictModel):
    data_source: Literal["synthetic", "local_export"]
    postings: list[PostingDocument] = Field(min_length=1)


class TargetScope(StrictModel):
    target_role: str = Field(min_length=1)
    seniority: Seniority
    country: str
    as_of: date
    window_days: int = Field(gt=0)


class ResumeCitation(StrictModel):
    path: str = Field(description="JSON pointer relative to the supplied reviewed_resume object")
    quote: str = Field(min_length=1)
    kind: Literal["listed", "applied", "validated"]


class ExtractedResumeSkill(StrictModel):
    skill: str
    citations: list[ResumeCitation]


class ResumeEvidenceExtraction(StrictModel):
    skills: list[ExtractedResumeSkill]


class JobRequirement(StrictModel):
    skill: str
    requirement: Literal["required", "preferred", "context", "negated"]
    quote: str = Field(min_length=1)


class ExtractedPosting(StrictModel):
    posting_id: str
    skills: list[JobRequirement]


class JobRequirementsExtraction(StrictModel):
    postings: list[ExtractedPosting]
