# Import every model here so Alembic's autogenerate can see it.
from app.models.job_posting import IngestRun, JobPosting
from app.models.resume import (
    Resume,
    ResumeAchievement,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    ResumeSkill,
)
from app.models.user import User

__all__ = [
    "IngestRun",
    "JobPosting",
    "Resume",
    "ResumeAchievement",
    "ResumeEducation",
    "ResumeExperience",
    "ResumeProject",
    "ResumeSkill",
    "User",
]
