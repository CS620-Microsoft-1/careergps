import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Requests: strip whitespace, reject unknown fields. Mirrors frontend/lib/validation/auth.ts,
# which only exists for user experience; these checks are the real ones.
REQUEST_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AccountCreate(BaseModel):
    """Sent once after the user has confirmed their email (POST /me). Sign-up asks only for
    email and password; the email comes from the token, so only the terms consent is sent."""

    model_config = REQUEST_CONFIG

    accept_terms: Literal[True]


class ProfileUpdate(BaseModel):
    """Fields onboarding can change (PATCH /me/profile). Goal fields are set at sign-up only."""

    model_config = REQUEST_CONFIG

    location: str = Field(min_length=1, max_length=100)


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
