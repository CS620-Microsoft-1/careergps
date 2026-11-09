"""Courses a student has taken (student_courses), and course codes found in a résumé.

A taken course stays in /resources (the plan needs it) and the browser hides it from the lists;
skill-gap scores don't change. The résumé match is plain regex, no model call: it only suggests
courses, and the student confirms before anything is written.
"""
from collections.abc import Iterable, Iterator
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import StudentCourse
from app.services import catalog_writes

logger = logging.getLogger(__name__)

# Other ways students write a subject code (after removing spaces and dots).
_SUBJECT_ALIASES = {"COMPSCI": ("CS", "CMPSCI", "COMPSCI"), "STAT": ("STATS", "STATISTICS"), "ECE": ("ECE",)}
_NUMBER = r"(?<!\d)\d{3}(?!\d)"
# "COMP SCI 400, 540 and 577" → 400, 540, 577
_LIST_TAIL = rf"(?:\s*(?:,|/|&|\band\b|\bor\b)\s*{_NUMBER})*"


def list_taken(session: Session, user_id: uuid.UUID) -> list[StudentCourse]:
    return list(session.scalars(select(StudentCourse).where(StudentCourse.user_id == user_id)
                                .order_by(StudentCourse.created_at, StudentCourse.course_id)))


def mark_taken(session: Session, user_id: uuid.UUID, course_id: str, source: str) -> StudentCourse:
    """Record a taken course and commit. Already recorded: keep the first row and its source.
    KeyError when the course isn't in school_courses (inactive rows are allowed)."""
    if catalog_writes.get_row(session, "school_course", course_id) is None:
        raise KeyError(course_id)
    session.execute(insert(StudentCourse).values(user_id=user_id, course_id=course_id, source=source)
                    .on_conflict_do_nothing(index_elements=["user_id", "course_id"]))
    session.commit()
    return session.get(StudentCourse, (user_id, course_id), populate_existing=True)


def record_done_course(session: Session, user_id: uuid.UUID, course_id: str) -> None:
    """A plan item marked done: record the course as taken. The plan is already saved, so a failure
    here (catalog not seeded yet, database down) is logged, not raised."""
    try:
        mark_taken(session, user_id, course_id, "plan")
    except (KeyError, SQLAlchemyError) as error:
        session.rollback()
        logger.warning("Could not record a done course as taken (%s)", type(error).__name__)


def unmark_taken(session: Session, user_id: uuid.UUID, course_id: str) -> None:
    row = session.get(StudentCourse, (user_id, course_id))
    if row is not None:
        session.delete(row)
        session.commit()


def _key(text: str) -> str:
    return re.sub(r"[\s.]", "", text.upper())


def _subject_pattern(subject: str) -> str:
    """"COMP SCI" → a regex that also matches "COMPSCI", "Comp. Sci." and the aliases."""
    key = _key(subject)
    spelled = r"[\s.]*".join(re.escape(char) for char in key)
    aliases = [re.escape(alias) for alias in _SUBJECT_ALIASES.get(key, ()) if alias != key]
    return "|".join([spelled, *aliases])


def _codes(course: dict) -> Iterator[tuple[str, str]]:
    """(subject, number) for each listing: "COMP SCI/E C E 552" → ("COMP SCI", "552"), ("E C E", "552")."""
    # Courses added by hand have no course_code; their title starts with it ("STAT 240: …").
    code = course.get("course_code") or course.get("title", "").split(":")[0]
    match = re.fullmatch(r"\s*(.+?)\s+(\d{3})\s*", code)
    if match:
        for subject in match.group(1).split("/"):
            yield subject.strip(), match.group(2)


def resume_strings(data) -> Iterator[str]:
    """Every string in confirmed résumé data."""
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from resume_strings(value)
    elif isinstance(data, list):
        for value in data:
            yield from resume_strings(value)


def match_courses(texts: Iterable[str], courses: Iterable[dict]) -> list[dict]:
    """Courses whose code appears in the texts, in course order."""
    courses = list(courses)
    by_code: dict[tuple[str, str], set[str]] = {}
    patterns: dict[str, str] = {}
    for course in courses:
        for subject, number in _codes(course):
            by_code.setdefault((_key(subject), number), set()).add(course["id"])
            patterns[_key(subject)] = _subject_pattern(subject)
    text = "\n".join(texts)
    found: set[str] = set()
    for subject, pattern in patterns.items():
        for match in re.finditer(rf"(?<![A-Za-z])(?:{pattern})[\s.]*({_NUMBER}{_LIST_TAIL})", text, re.IGNORECASE):
            for number in re.findall(_NUMBER, match.group(1)):
                found |= by_code.get((subject, number), set())
    return [course for course in courses if course["id"] in found]
