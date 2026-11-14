"""Courses a student has taken (student_courses), and courses found in a résumé.

A taken course stays in /resources (the plan needs it) and the browser hides it from the lists;
skill-gap scores don't change. The résumé match is plain regex, no model call: it only suggests
courses, and the student confirms before anything is written. Courses are found by name
("Operating Systems"), and only where the résumé lists courses, because many names are also
everyday phrases ("Machine Learning"). Course codes ("CS 400") are not looked for.
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
from app.services.resources import same_school

logger = logging.getLogger(__name__)

# A string outside the education entries counts as a course list when it says one of these.
_COURSE_LIST = re.compile(r"\b(?:coursework|courses)\b", re.IGNORECASE)
# Students drop it: "Operating Systems" for "Introduction to Operating Systems".
_INTRO = re.compile(r"^introduction to ")


def list_taken(session: Session, user_id: uuid.UUID) -> list[StudentCourse]:
    return list(session.scalars(select(StudentCourse).where(StudentCourse.user_id == user_id)
                                .order_by(StudentCourse.created_at, StudentCourse.course_id)))


def mark_taken(session: Session, user_id: uuid.UUID, course_id: str, source: str,
               university: str | None) -> StudentCourse:
    """Record a taken course and commit. Already recorded: keep the first row and its source.
    KeyError when the course isn't in school_courses or belongs to another school than the
    student's university (inactive rows are allowed)."""
    course = catalog_writes.get_row(session, "school_course", course_id)
    if course is None or not same_school(course.school, university):
        raise KeyError(course_id)
    session.execute(insert(StudentCourse).values(user_id=user_id, course_id=course_id, source=source)
                    .on_conflict_do_nothing(index_elements=["user_id", "course_id"]))
    session.commit()
    return session.get(StudentCourse, (user_id, course_id), populate_existing=True)


def record_done_course(session: Session, user_id: uuid.UUID, course_id: str, university: str | None) -> None:
    """A plan item marked done: record the course as taken. The plan is already saved, so a failure
    here (catalog not seeded yet, database down) is logged, not raised."""
    try:
        mark_taken(session, user_id, course_id, "plan", university)
    except (KeyError, SQLAlchemyError) as error:
        session.rollback()
        logger.warning("Could not record a done course as taken (%s)", type(error).__name__)


def unmark_taken(session: Session, user_id: uuid.UUID, course_id: str) -> None:
    row = session.get(StudentCourse, (user_id, course_id))
    if row is not None:
        session.delete(row)
        session.commit()


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


def course_list_strings(data) -> Iterator[str]:
    """Résumé text that lists courses: everything under an education entry, and any other string
    that says "coursework" or "courses"."""
    if not isinstance(data, dict):
        return
    education = data.get("education")
    for entry in education if isinstance(education, list) else ():
        if isinstance(entry, dict):
            yield from resume_strings(entry.get("content"))
    for text in resume_strings(data):
        if _COURSE_LIST.search(text):
            yield text


def _name_key(text: str) -> str:
    """Lower-case words with single spaces; list punctuation becomes "|", so a name can't run
    from one list item into the next: "Coursework: Algorithms, Operating Systems" →
    "coursework | algorithms | operating systems". "Intro" is spelled out."""
    text = text.lower().replace("&", " and ").replace("'", "").replace("’", "")
    text = re.sub(r"\bintro\b\.?", "introduction", text)
    text = re.sub(r"[,;:|/()\[\]•·\n]|\.(?=\s|$)", " | ", text)
    return " ".join(re.sub(r"[^a-z0-9|]+", " ", text).split())


def _names(course: dict) -> set[str]:
    """The ways a course's name is written, as _name_key keys: the full name, the part before a
    colon, without "(…)", and each without a leading "Introduction to"."""
    title = course.get("title", "")
    head, colon, rest = title.partition(":")
    # Titles start with the code: "COMP SCI 564: Database Management Systems: Design and Implementation".
    name = rest if colon and re.fullmatch(r"\s*.+?\s+\d{3}\s*", head) else title
    keys = set()
    for spelling in (name, name.split(":")[0], re.sub(r"\([^)]*\)", " ", name)):
        key = _name_key(spelling).strip("| ")
        keys |= {key, _INTRO.sub("", key)}
    return keys - {""}


def _number(course: dict) -> tuple[int, str]:
    """Sort key: the course number, so the lowest-numbered course wins a shared name."""
    # Courses added by hand have no course_code; their title starts with it ("STAT 240: …").
    code = course.get("course_code") or course.get("title", "").split(":")[0]
    match = re.search(r"(\d{3})\s*$", code)
    return (int(match.group(1)) if match else 10**6), course["id"]


def match_courses(course_lists: Iterable[str], courses: Iterable[dict]) -> list[dict]:
    """Courses whose name appears in the course lists (course_list_strings), in course order.

    - Whole words only, inside one list item. A one-word name ("Algorithms") must be the whole item.
    - A name inside a longer matched name doesn't count: "Matrix Methods in Machine Learning" is
      not also "Machine Learning".
    - A name several courses share ("Computer Vision": 566 and 766) gives the lowest-numbered one.
    """
    courses = list(courses)
    by_name: dict[str, list[dict]] = {}
    for course in courses:
        for name in _names(course):
            by_name.setdefault(name, []).append(course)
    found: set[str] = set()
    for text in course_lists:
        key = _name_key(text)
        spans = []
        for name in by_name:
            escaped = re.escape(name)
            pattern = (rf"(?<![^ ]){escaped}(?![^ ])" if " " in name
                       else rf"(?:^|(?<=\| )){escaped}(?= \||$)")
            spans += [(match.start(), match.end(), name) for match in re.finditer(pattern, key)]
        for start, end, name in spans:
            inside_longer = any(other_start <= start and end <= other_end and other_end - other_start > end - start
                                for other_start, other_end, _ in spans)
            if not inside_longer:
                found.add(min(by_name[name], key=_number)["id"])
    return [course for course in courses if course["id"] in found]
