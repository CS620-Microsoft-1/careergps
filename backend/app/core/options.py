"""Fixed choices offered in onboarding. Keep in sync with frontend/lib/options.ts."""
from typing import Literal, get_args

TargetRole = Literal["Software Engineer", "Data Analyst", "AI Engineer"]
ExperienceLevel = Literal["Internship", "Full-time"]

TARGET_ROLES: tuple[str, ...] = get_args(TargetRole)
EXPERIENCE_LEVELS: tuple[str, ...] = get_args(ExperienceLevel)

# Graduation year: this year plus the next four (frontend/lib/graduation-years.ts).
GRADUATION_YEARS_AHEAD = 4

# Onboarding doesn't ask for the university yet; users.university is required, so new users get this.
DEFAULT_UNIVERSITY = "University of Wisconsin–Madison"
