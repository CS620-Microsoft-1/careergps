"""Courses a student has taken (student_courses), and courses found in a résumé.

A taken course stays in /resources (the plan needs it) and the browser hides it from the lists;
skill-gap scores don't change. The résumé match is plain regex, no model call: it only suggests
courses, and the student confirms before anything is written. Courses are found by name
("Operating Systems") or by code ("CS 400"), and only where the résumé lists courses, because
many names are also everyday phrases ("Machine Learning").
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

# A string outside the education entries is a course list from a line that starts with one of
# these. Anywhere else the word is ordinary prose: "Built a site that ranks UW courses".
_COURSE_LIST = re.compile(r"^[^\w\n]*(?:relevant\s+)?(?:coursework|courses)\b", re.IGNORECASE | re.MULTILINE)
# Students drop it: "Operating Systems" for "Introduction to Operating Systems".
_INTRO = re.compile(r"^introduction to ")
# Other ways students write a subject code (after removing spaces and dots).
_SUBJECT_ALIASES = {"COMPSCI": ("CS", "CMPSCI", "COMPSCI"), "STAT": ("STATS", "STATISTICS"), "ECE": ("ECE",)}
_NUMBER = r"(?<!\d)\d{3}(?!\d)"
# "COMP SCI 400, 540 and 577" → 400, 540, 577
_LIST_TAIL = rf"(?:\s*(?:,|/|&|\band\b|\bor\b)\s*{_NUMBER})*"


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
    from a line that starts with "Coursework" / "Courses" / "Relevant coursework" on."""
    if not isinstance(data, dict):
        return
    education = data.get("education")
    listed: set[str] = set()
    for entry in education if isinstance(education, list) else ():
        if isinstance(entry, dict):
            for text in resume_strings(entry.get("content")):
                listed.add(text)
                yield text
    for text in resume_strings(data):
        heading = _COURSE_LIST.search(text)
        if heading and text not in listed:
            yield text[heading.start():]


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


def _code_matches(course_lists: list[str], courses: list[dict]) -> set[str]:
    """Ids of the courses whose code appears in the course lists: "CS 400", "Comp. Sci. 400, 540"."""
    by_code: dict[tuple[str, str], set[str]] = {}
    patterns: dict[str, str] = {}
    for course in courses:
        for subject, number in _codes(course):
            by_code.setdefault((_key(subject), number), set()).add(course["id"])
            patterns[_key(subject)] = _subject_pattern(subject)
    found: set[str] = set()
    text = "\n".join(course_lists)
    for subject, pattern in patterns.items():
        for match in re.finditer(rf"(?<![A-Za-z])(?:{pattern})[\s.]*({_NUMBER}{_LIST_TAIL})", text, re.IGNORECASE):
            for number in re.findall(_NUMBER, match.group(1)):
                found |= by_code.get((subject, number), set())
    return found


def match_courses(course_lists: Iterable[str], courses: Iterable[dict]) -> list[dict]:
    """Courses whose name or code appears in the course lists (course_list_strings), in course
    order. A code is any way students write it ("CS 400", "COMP SCI 400, 540 and 577"). A name:

    - Whole words only, inside one list item. A one-word name ("Algorithms") must be the whole item.
    - A name inside a longer matched name doesn't count: "Matrix Methods in Machine Learning" is
      not also "Machine Learning".
    - A name several courses share ("Computer Vision": 566 and 766) gives the lowest-numbered one.
    """
    courses, course_lists = list(courses), list(course_lists)
    by_name: dict[str, list[dict]] = {}
    for course in courses:
        for name in _names(course):
            by_name.setdefault(name, []).append(course)
    found = _code_matches(course_lists, courses)
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
