"""Résumé data shapes.

ResumeExtraction is what the LLM must return. It has no length or format constraints because
Azure OpenAI structured outputs only support a subset of JSON Schema; every field is required
but may be null or an empty list. ResumeConfirm is the same shape as edited and sent back by the
user, and is validated strictly before anything is written to the structured tables.
"""
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SkillCategory = Literal["language", "framework", "tool", "other"]


# --- LLM output ---------------------------------------------------------------------------


class ExtractedContact(BaseModel):
    full_name: str | None
    email: str | None
    phone: str | None
    location: str | None
    links: list[str]


class ExtractedEducation(BaseModel):
    school: str
    degree: str | None
    field_of_study: str | None
    start_date: str | None = Field(description='"YYYY" or "YYYY-MM", or null')
    end_date: str | None = Field(description='"YYYY" or "YYYY-MM", or null')
    gpa: str | None


class ExtractedExperience(BaseModel):
    company: str
    title: str | None
    location: str | None
    start_date: str | None = Field(description='"YYYY" or "YYYY-MM", or null')
    end_date: str | None = Field(description='"YYYY" or "YYYY-MM", or null if current')
    is_current: bool
    bullets: list[str]


class ExtractedProject(BaseModel):
    name: str
    description: str | None
    url: str | None
    technologies: list[str]


class ExtractedSkill(BaseModel):
    name: str
    category: SkillCategory


class ResumeExtraction(BaseModel):
    contact: ExtractedContact
    education: list[ExtractedEducation]
    experience: list[ExtractedExperience]
    projects: list[ExtractedProject]
    skills: list[ExtractedSkill]


# --- User-confirmed data --------------------------------------------------------------------

CONFIRM_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")

ResumeDate = Annotated[str, Field(pattern=r"^\d{4}(-(0[1-9]|1[0-2]))?$")]


def text(max_length: int):
    return Annotated[str, Field(min_length=1, max_length=max_length)]


class ConfirmContact(BaseModel):
    model_config = CONFIRM_CONFIG

    full_name: text(100) | None = None
    email: text(255) | None = None
    phone: text(50) | None = None
    location: text(100) | None = None
    links: list[text(500)] = Field(default_factory=list, max_length=10)


class ConfirmEducation(BaseModel):
    model_config = CONFIRM_CONFIG

    school: text(200)
    degree: text(200) | None = None
    field_of_study: text(200) | None = None
    start_date: ResumeDate | None = None
    end_date: ResumeDate | None = None
    gpa: text(20) | None = None


class ConfirmExperience(BaseModel):
    model_config = CONFIRM_CONFIG

    company: text(200)
    title: text(200) | None = None
    location: text(200) | None = None
    start_date: ResumeDate | None = None
    end_date: ResumeDate | None = None
    is_current: bool = False
    bullets: list[text(1000)] = Field(default_factory=list, max_length=30)


class ConfirmProject(BaseModel):
    model_config = CONFIRM_CONFIG

    name: text(200)
    description: text(2000) | None = None
    url: text(500) | None = None
    technologies: list[text(100)] = Field(default_factory=list, max_length=30)


class ConfirmSkill(BaseModel):
    model_config = CONFIRM_CONFIG

    name: text(100)
    category: SkillCategory = "other"


class ResumeConfirm(BaseModel):
    model_config = CONFIRM_CONFIG

    contact: ConfirmContact = Field(default_factory=ConfirmContact)
    education: list[ConfirmEducation] = Field(default_factory=list, max_length=20)
    experience: list[ConfirmExperience] = Field(default_factory=list, max_length=30)
    projects: list[ConfirmProject] = Field(default_factory=list, max_length=30)
    skills: list[ConfirmSkill] = Field(default_factory=list, max_length=200)


# --- Responses ------------------------------------------------------------------------------


class ResumeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    error_code: str | None
    original_filename: str
    created_at: datetime


class ResumeRead(ResumeSummary):
    """parsed_data is the LLM's ResumeExtraction until confirmed, then what the user confirmed."""

    parsed_data: dict | None
