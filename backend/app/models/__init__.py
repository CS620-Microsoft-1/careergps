# Import every model here so Alembic's autogenerate can see it.
from app.models.job_posting import IngestRun, JobPosting
from app.models.profile import Profile
from app.models.resume_profile import ResumeProfile
from app.models.user import User

__all__ = ["IngestRun", "JobPosting", "Profile", "ResumeProfile", "User"]
