"""Which school courses the Resources page lists, from the course guide's Last Taught.

A course not taught in the last RECENT_SEMESTERS fall/spring semesters is hidden. Summer sessions
count as recent but do not count toward the window. A course without Last Taught (new, or added by
hand) is always listed. Graduate courses are listed like any other.

The semesters are counted back from the day the course guide data was retrieved, not from today:
Last Taught is as old as that data, so counting from today would hide more courses every semester
until someone refreshes it (backend/README.md, "UW–Madison courses").
"""
from datetime import date
import re

from app.services import uw_courses

RECENT_SEMESTERS = 4

# Order within a year.
_TERMS = {"spring": 1, "summer": 2, "fall": 3}
_TERM = re.compile(r"\b(spring|summer|fall)\s+(\d{4})\b", re.IGNORECASE)

Term = tuple[int, int]  # (year, _TERMS value)


def parse_term(text: str | None) -> Term | None:
    """"Fall 2025" → (2025, 3); None when the text has no term."""
    match = _TERM.search(text or "")
    return (int(match.group(2)), _TERMS[match.group(1).lower()]) if match else None


def current_semester(today: date) -> Term:
    """The fall or spring semester under way, or the spring just finished during the summer."""
    if today.month >= 9:
        return today.year, _TERMS["fall"]
    return today.year, _TERMS["spring"]


def recent_cutoff(today: date) -> Term:
    """The oldest of the last RECENT_SEMESTERS fall/spring semesters, counting the current one."""
    year, term = current_semester(today)
    for _ in range(RECENT_SEMESTERS - 1):
        year, term = (year, _TERMS["spring"]) if term == _TERMS["fall"] else (year - 1, _TERMS["fall"])
    return year, term


def reference_date() -> date:
    """The day the window is counted back from: when the course guide data was retrieved, or today
    when there is no such data. Tests patch this to pin the date."""
    return uw_courses.snapshot_date() or date.today()


def is_listed(entry: dict, on: date | None = None) -> bool:
    taught = parse_term(entry.get("last_taught"))
    return taught is None or taught >= recent_cutoff(on or reference_date())
