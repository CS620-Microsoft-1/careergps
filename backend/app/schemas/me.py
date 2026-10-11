import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.options import GRADUATION_YEARS_AHEAD, ExperienceLevel, TargetRole

# Requests: strip whitespace, reject unknown fields. Mirrors frontend/lib/validation/auth.ts,
# which only exists for user experience; these checks are the real ones.
REQUEST_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AccountCreate(BaseModel):
    """Sign-up fields, sent once after the user has confirmed their email (POST /me)."""

    model_config = REQUEST_CONFIG

    full_name: str = Field(min_length=1, max_length=100)
    target_role: TargetRole
    graduation_year: int
    university: str = Field(min_length=1, max_length=150)
    experience_level: ExperienceLevel
    accept_terms: Literal[True]

    @field_validator("graduation_year")
    @classmethod
    def graduation_year_in_range(cls, year: int) -> int:
        this_year = date.today().year
        if not this_year <= year <= this_year + GRADUATION_YEARS_AHEAD:
            raise ValueError(
                f"must be between {this_year} and {this_year + GRADUATION_YEARS_AHEAD}"
            )
        return year


class ProfileUpdate(BaseModel):
    """Fields onboarding can change (PATCH /me/profile). Goal fields are set at sign-up only."""

    model_config = REQUEST_CONFIG

    location: str = Field(min_length=1, max_length=100)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    created_at: datetime


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_role: str
    experience_level: str
    graduation_year: int
    university: str
    location: str | None
    onboarding_completed_at: datetime | None


class MeRead(BaseModel):
    """Both are null until POST /me succeeds; the frontend uses that to finish sign-up."""

    user: UserRead | None
    profile: ProfileRead | None
