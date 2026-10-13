from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PostingSource = Literal["greenhouse", "ashby", "lever"]
WorkplaceType = Literal["onsite", "hybrid", "remote"]
EmploymentType = Literal["full_time", "part_time", "contract", "intern", "temporary"]
SalaryInterval = Literal["year", "month", "week", "day", "hour"]
Seniority = Literal["intern", "entry", "mid", "senior"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NormalizedPosting(StrictModel):
    """One open posting from any job board, mapped to a single shape before storage."""

    source: PostingSource
    external_id: str
    title: str
    location: str | None
    country: str | None = Field(description="ISO 3166-1 alpha-2 code when the source states it")
    workplace_type: WorkplaceType | None
    department: str | None
    employment_type: EmploymentType | None
    description_text: str
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_interval: SalaryInterval | None
    url: str
    published_at: datetime | None


class DateWindow(StrictModel):
    start: date
    end: date
    days: int


class SkillDemand(StrictModel):
    name: str
    postings: int
    frequency: float = Field(description="Share of postings in the window that mention the skill, 0 to 1")
    previous_frequency: float | None = Field(description="Same share in the preceding window, when available")
    example_posting_ids: list[UUID]


class SalarySummary(StrictModel):
    currency: str
    interval: SalaryInterval
    p25: int
    median: int
    p75: int
    sample_size: int


class SponsorshipBreakdown(StrictModel):
    sponsors: int
    no_sponsorship: int
    citizenship_required: int
    unknown: int


class MarketProfile(StrictModel):
    """Market statistics for one role and seniority, computed from stored postings."""

    role: str
    seniority: Seniority
    window: DateWindow
    sample_size: int
    company_count: int
    low_confidence: bool
    skills: list[SkillDemand]
    salary: SalarySummary | None
    sponsorship: SponsorshipBreakdown
