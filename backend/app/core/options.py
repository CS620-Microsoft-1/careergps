"""Fixed choices offered in onboarding. Keep in sync with frontend/lib/options.ts."""
from typing import Literal, get_args

TargetRole = Literal["Software Engineer", "Data Analyst", "AI Engineer"]
ExperienceLevel = Literal["Internship", "Full-time"]

TARGET_ROLES: tuple[str, ...] = get_args(TargetRole)

# Each target role is one destination; the analysis and résumés use its job family id.
JobFamily = Literal["software_engineer", "data_analyst", "ai_engineer"]
JOB_FAMILY_BY_ROLE: dict[str, JobFamily] = {
    "Software Engineer": "software_engineer",
    "Data Analyst": "data_analyst",
    "AI Engineer": "ai_engineer",
}
JOB_FAMILIES: tuple[str, ...] = get_args(JobFamily)
EXPERIENCE_LEVELS: tuple[str, ...] = get_args(ExperienceLevel)

# Graduation year: this year plus the next four (frontend/lib/graduation-years.ts).
GRADUATION_YEARS_AHEAD = 4
