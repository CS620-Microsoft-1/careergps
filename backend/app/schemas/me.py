import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.options import GRADUATION_YEARS_AHEAD, ExperienceLevel, JobFamily, TargetRole
from app.schemas.resume import ResumeClassification

# Requests: strip whitespace, reject unknown fields. Mirrors frontend/lib/validation/auth.ts,
# which only exists for user experience; these checks are the real ones.
REQUEST_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _check_graduation_year(year: int | None) -> int | None:
    # Matches ck_users_graduation_year_range (2000-2100), capped at the onboarding list's last year.
    latest = datetime.now().year + GRADUATION_YEARS_AHEAD
    if year is not None and not 2000 <= year <= latest:
        raise ValueError(f"graduation_year must be between 2000 and {latest}")
    return year


class ResumeSubmit(BaseModel):
    """A résumé the student confirmed on the review page, with how POST /resumes/analyze read it."""

    model_config = REQUEST_CONFIG

    original_filename: str = Field(min_length=1, max_length=255, pattern=r"(?i)\.(pdf|docx)$")
    parser: str = Field(min_length=1, max_length=50)
    ocr_pages: list[int] = Field(default_factory=list)
    agent_name: str = Field(min_length=1, max_length=255)
    classification: ResumeClassification


class ResumeAdd(ResumeSubmit):
    """POST /me/resumes: a confirmed résumé, used from now on by this destination (added if new).
    The résumé it used before is kept."""

    job_family: JobFamily


class DestinationUpdate(BaseModel):
    """PUT /me/destinations/{job_family}: match the role against one of the student's résumés."""

    model_config = REQUEST_CONFIG

    resume_id: uuid.UUID


class AccountCreate(BaseModel):
    """POST /me: the end of onboarding. Creates the users row and the first résumé together.

    The email comes from the token. The university is pre-filled from the résumé on the review
    page, so the student confirms it.
    """

    model_config = REQUEST_CONFIG

    accept_terms: Literal[True]
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    university: str = Field(min_length=1, max_length=150)
    target_role: TargetRole
    experience_level: ExperienceLevel
    graduation_year: int
    preferred_location: str = Field(min_length=1, max_length=100)
    resume: ResumeSubmit

    @field_validator("graduation_year")
    @classmethod
    def _plausible_year(cls, year: int | None) -> int | None:
        return _check_graduation_year(year)


class AccountUpdate(BaseModel):
    """PATCH /me: change the name, university or career goal. Only the fields sent change."""

    model_config = REQUEST_CONFIG

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    university: str | None = Field(default=None, min_length=1, max_length=150)

    target_role: TargetRole | None = None
    experience_level: ExperienceLevel | None = None
    graduation_year: int | None = None
    preferred_location: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("graduation_year")
    @classmethod
    def _plausible_year(cls, year: int | None) -> int | None:
        return _check_graduation_year(year)

    @model_validator(mode="after")
    def _no_nulls(self) -> "AccountUpdate":
        # None only means "not sent". An explicit null would write NULL into a NOT NULL column.
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} can't be null; leave it out to keep the current value")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    primary_email: str
    first_name: str
    last_name: str
    full_name: str | None
    target_role: str
    experience_level: str
    graduation_year: int
    university: str
    preferred_location: str
    resume_emails: list[str]
    phones: list[str]
    current_location: str | None
    linkedin_url: str | None
    github_url: str | None
    website_url: str | None
    created_at: datetime


class MeRead(BaseModel):
    """user is null until onboarding is finished (POST /me); the frontend uses that to send people there."""

    user: UserRead | None


class ResumeSummary(BaseModel):
    """GET /me/resumes: one saved version, without its contents."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str | None
    original_filename: str
    file_type: str
    created_at: datetime
    # The roles matched against this résumé; empty for a version no destination uses.
    destinations: list[JobFamily]


class DestinationRead(BaseModel):
    """GET /me/destinations: one role the student added and the résumé it uses."""

    job_family: JobFamily
    resume_id: uuid.UUID
    original_filename: str
    created_at: datetime


class ResumeRead(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_type: str
    classification: ResumeClassification
    created_at: datetime
