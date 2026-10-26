"""Fixed choices offered in onboarding. Keep in sync with frontend/lib/options.ts."""
from typing import Literal, get_args

TargetRole = Literal["Software Engineer", "Data Analyst", "AI Engineer"]
ExperienceLevel = Literal["Internship", "Full-time"]

TARGET_ROLES: tuple[str, ...] = get_args(TargetRole)
EXPERIENCE_LEVELS: tuple[str, ...] = get_args(ExperienceLevel)

# Graduation year: this year plus the next four (frontend/lib/graduation-years.ts).
GRADUATION_YEARS_AHEAD = 4
