from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TakenCourse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: str
    # The Taken button, a confirmed résumé match, or a plan item marked done.
    source: Literal["manual", "resume", "plan"]
    created_at: datetime


class TakenCourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "resume" when the student confirms a match from GET /me/courses/resume-matches.
    source: Literal["manual", "resume"] = "manual"


class TakenCourseList(BaseModel):
    courses: list[TakenCourse]


class ResumeCourseMatches(BaseModel):
    """School course ids found in the résumé, not yet marked taken."""

    course_ids: list[str]
