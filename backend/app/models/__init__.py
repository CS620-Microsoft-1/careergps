# Import every model here so Alembic's autogenerate can see it.
from app.models.destination import Destination
from app.models.job_posting import IngestRun, JobPosting
from app.models.job_posting_analysis import (
    JobAnalysisCompensation,
    JobAnalysisCondition,
    JobAnalysisLocation,
    JobAnalysisQualification,
    JobAnalysisResponsibility,
    JobPostingAnalysis,
)
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
    "Destination",
    "JobPostingAnalysis",
    "JobAnalysisLocation",
    "JobAnalysisResponsibility",
    "JobAnalysisQualification",
    "JobAnalysisCondition",
    "JobAnalysisCompensation",
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
