import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.options import GRADUATION_YEARS_AHEAD, ExperienceLevel, TargetRole

# Requests: strip whitespace, reject unknown fields. Mirrors frontend/lib/validation/auth.ts,
# which only exists for user experience; these checks are the real ones.
REQUEST_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AccountCreate(BaseModel):
    """Sent once after the user has confirmed their email (POST /me). Sign-up asks only for
    email and password; the email comes from the token, so only the terms consent is sent."""

    model_config = REQUEST_CONFIG

    accept_terms: Literal[True]


class ProfileUpdate(BaseModel):
    """What onboarding saves (PATCH /me/profile). Every field is optional; only the ones sent change.

    full_name lives on users; the rest on profiles. complete_onboarding stamps
    onboarding_completed_at the first time it is sent.
    """

    model_config = REQUEST_CONFIG

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    target_role: TargetRole | None = None
    experience_level: ExperienceLevel | None = None
    graduation_year: int | None = None
    university: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    complete_onboarding: Literal[True] | None = None

    @field_validator("graduation_year")
    @classmethod
    def _plausible_year(cls, year: int | None) -> int | None:
        # Past years are fine (already graduated); the future is capped like the onboarding list.
        latest = datetime.now().year + GRADUATION_YEARS_AHEAD
        if year is not None and not 1950 <= year <= latest:
            raise ValueError(f"graduation_year must be between 1950 and {latest}")
        return year


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    created_at: datetime


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_role: str | None
    experience_level: str | None
    graduation_year: int | None
    university: str | None
    location: str | None
    onboarding_completed_at: datetime | None


class MeRead(BaseModel):
    """user and profile are null until POST /me succeeds; the frontend uses that to finish sign-up."""

    user: UserRead | None
    profile: ProfileRead | None
