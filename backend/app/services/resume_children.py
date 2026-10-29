"""Rows of the résumé child tables, derived from resumes.confirmed_data.

confirmed_data stays the source of truth; the child tables are rebuilt from it so agents can query
the parts they need in SQL. The rules that don't need the database are plain functions so they can be
tested without one.
"""
import re
import unicodedata
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    Resume,
    ResumeAchievement,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    ResumeSkill,
)
from app.schemas.resume import (
    AwardEntry,
    CertificationEntry,
    EducationEntry,
    LeadershipEntry,
    ProjectEntry,
    ResearchExperienceEntry,
    ResumeClassification,
    WorkExperienceEntry,
)

# Month used for a year-only date ("2022"), as documented on the child models.
START_MONTH = 1
EXPERIENCE_END_MONTH = 12
EDUCATION_END_MONTH = 5  # the usual graduation month

CURRENT_END_DATES = {"present", "current", "now"}

_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}

# Checked in this order, so "Master of Science" never matches a bachelor abbreviation.
_DEGREE_WORDS = (
    ("doctorate", {"phd", "dphil", "edd", "doctor", "doctorate", "doctoral"}),
    ("master", {"master", "masters", "ms", "msc", "ma", "mba", "meng", "mph", "mfa", "mtech", "mcs", "mres"}),
    ("bachelor", {"bachelor", "bachelors", "bs", "bsc", "ba", "beng", "btech", "bba", "bse", "bfa"}),
    ("associate", {"associate", "associates", "aa", "aas"}),
)

# Numeric(5, 2) holds values below 1000.
_GPA_LIMIT = Decimal("1000")
_GPA = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?")


def _column_length(model: type[Base], column: str) -> int:
    return model.__table__.c[column].type.length


def _fit_text(value: str | None, model: type[Base], column: str) -> str | None:
    """Trimmed and cut to the column's length; the résumé contract has no length limits."""
    value = (value or "").strip()
    return value[: _column_length(model, column)] or None


def _fit_url(value: str | None, model: type[Base], column: str) -> str | None:
    """A URL longer than its column is dropped rather than cut, since a cut URL doesn't work."""
    value = (value or "").strip()
    return value if value and len(value) <= _column_length(model, column) else None


def _clean_lines(lines: list[str]) -> list[str]:
    """Bullet points without surrounding whitespace or empty lines."""
    return [line.strip() for line in lines if line.strip()]


def _valid_month(year: int, month: int) -> date | None:
    return date(year, month, 1) if 1900 <= year <= 2100 and 1 <= month <= 12 else None


def parse_month(value: str | None, year_only_month: int) -> tuple[date | None, str | None]:
    """(first day of the month, 'month' | 'year') for "2024-05", "05/2024", "May 2024" or "2024".

    A year-only date uses year_only_month. Anything else, including "Present", gives (None, None).
    """
    text = (value or "").strip().lower()
    if match := re.fullmatch(r"(\d{4})-(\d{1,2})", text):
        month = _valid_month(int(match[1]), int(match[2]))
    elif match := re.fullmatch(r"(\d{1,2})/(\d{4})", text):
        month = _valid_month(int(match[2]), int(match[1]))
    elif (match := re.fullmatch(r"([a-z]+)\.?,?\s+(\d{4})", text)) and match[1] in _MONTHS:
        month = _valid_month(int(match[2]), _MONTHS[match[1]])
    elif match := re.fullmatch(r"\d{4}", text):
        month = _valid_month(int(text), year_only_month)
        return (month, "year") if month else (None, None)
    else:
        return None, None
    return (month, "month") if month else (None, None)


def is_current(end_date: str | None) -> bool:
    return (end_date or "").strip().lower() in CURRENT_END_DATES


def parse_degree_level(degree: str | None) -> str | None:
    """associate, bachelor, master or doctorate from the degree's wording; 'other' if none match."""
    words = set(re.findall(r"[a-z]+", (degree or "").lower().replace(".", "")))
    if not words:
        return None
    for level, keywords in _DEGREE_WORDS:
        if words & keywords:
            return level
    return "other"


def parse_gpa(gpa: str | None) -> tuple[Decimal | None, Decimal | None]:
    """(value, scale) from "3.8/4.0" or "3.8"; the scale is None when it isn't given or isn't positive."""
    match = _GPA.search(gpa or "")
    if match is None:
        return None, None
    try:
        value = Decimal(match[1]).quantize(Decimal("0.01"))
        scale = Decimal(match[2]).quantize(Decimal("0.01")) if match[2] else None
    except InvalidOperation:
        return None, None
    if value >= _GPA_LIMIT:
        return None, None
    if scale is not None and not 0 < scale < _GPA_LIMIT:
        scale = None
    return value, scale


def normalize_skill(name: str) -> str:
    """Join key with market skills: Unicode-normalized, single-spaced, lowercase, cut to the column.

    No aliases yet, so "Postgres" and "PostgreSQL" stay different.
    """
    normalized = " ".join(unicodedata.normalize("NFKC", name).split()).lower()
    return normalized[: _column_length(ResumeSkill, "normalized_name")]


def _precision(*precisions: str | None) -> str | None:
    """The coarser of the row's parsed dates: 'year' if any is year-only, None if none parsed."""
    parsed = [p for p in precisions if p]
    return ("year" if "year" in parsed else "month") if parsed else None


def _experience(
    entry: WorkExperienceEntry | ResearchExperienceEntry | LeadershipEntry, kind: str, position: int, owner: dict
) -> ResumeExperience | None:
    organization = entry.company if isinstance(entry, WorkExperienceEntry) else entry.organization
    title = entry.role if isinstance(entry, LeadershipEntry) else entry.title
    row = ResumeExperience(
        id=uuid.uuid4(),
        **owner,
        kind=kind,
        position=position,
        organization=_fit_text(organization, ResumeExperience, "organization"),
        title=_fit_text(title, ResumeExperience, "title"),
        location=_fit_text(entry.location, ResumeExperience, "location"),
        content=_clean_lines(entry.content),
        start_date=_fit_text(entry.start_date, ResumeExperience, "start_date"),
        end_date=_fit_text(entry.end_date, ResumeExperience, "end_date"),
        is_current=is_current(entry.end_date),
    )
    # ck_resume_experiences_not_blank
    if row.organization is None and row.title is None and not row.content:
        return None
    row.start_month, start_precision = parse_month(entry.start_date, START_MONTH)
    row.end_month, end_precision = parse_month(entry.end_date, EXPERIENCE_END_MONTH)
    row.date_precision = _precision(start_precision, end_precision)
    return row


def _education(entry: EducationEntry, position: int, owner: dict) -> ResumeEducation | None:
    row = ResumeEducation(
        id=uuid.uuid4(),
        **owner,
        position=position,
        institution=_fit_text(entry.institution, ResumeEducation, "institution"),
        degree=_fit_text(entry.degree, ResumeEducation, "degree"),
        major=_fit_text(entry.major, ResumeEducation, "major"),
        gpa=_fit_text(entry.gpa, ResumeEducation, "gpa"),
        content=_clean_lines(entry.content),
        start_date=_fit_text(entry.start_date, ResumeEducation, "start_date"),
        end_date=_fit_text(entry.end_date, ResumeEducation, "end_date"),
        degree_level=parse_degree_level(entry.degree),
    )
    # ck_resume_educations_not_blank
    if row.institution is None and row.degree is None and row.major is None:
        return None
    row.gpa_value, row.gpa_scale = parse_gpa(entry.gpa)
    row.start_month, start_precision = parse_month(entry.start_date, START_MONTH)
    row.end_month, end_precision = parse_month(entry.end_date, EDUCATION_END_MONTH)
    row.date_precision = _precision(start_precision, end_precision)
    return row


def _project(entry: ProjectEntry, position: int, owner: dict) -> ResumeProject | None:
    row = ResumeProject(
        id=uuid.uuid4(),
        **owner,
        position=position,
        name=_fit_text(entry.name, ResumeProject, "name"),
        url=_fit_url(entry.url, ResumeProject, "url"),
        technologies=_clean_lines(entry.technologies),
        content=_clean_lines(entry.content),
    )
    # ck_resume_projects_not_blank
    return row if row.name is not None or row.content else None


def _achievement(
    entry: CertificationEntry | AwardEntry, kind: str, position: int, owner: dict
) -> ResumeAchievement | None:
    name = _fit_text(entry.name, ResumeAchievement, "name")
    if name is None:  # name is NOT NULL
        return None
    issued_month, precision = parse_month(entry.date, START_MONTH)
    return ResumeAchievement(
        id=uuid.uuid4(),
        **owner,
        kind=kind,
        position=position,
        name=name,
        issuer=_fit_text(entry.issuer, ResumeAchievement, "issuer"),
        # Awards have no URL in the contract (ck_resume_achievements_url).
        url=_fit_url(entry.url, ResumeAchievement, "url") if isinstance(entry, CertificationEntry) else None,
        content=_clean_lines(entry.content),
        issued_date=_fit_text(entry.date, ResumeAchievement, "issued_date"),
        issued_month=issued_month,
        date_precision=precision,
    )


def _skills(technical_skills: list[str], projects: list[ResumeProject], owner: dict) -> list[ResumeSkill]:
    """'listed' evidence from Technical Skills and 'project' evidence from each project's technologies.

    One row per (normalized_name, source, project), as uq_resume_skills_evidence requires; the first
    spelling wins. Skills found in experience, education or certification text come later.
    """
    candidates = [(name, "listed", position, None) for position, name in enumerate(technical_skills)]
    candidates += [(name, "project", None, project.id) for project in projects for name in project.technologies]
    skills, seen = [], set()
    for raw_name, source, position, project_id in candidates:
        name = _fit_text(raw_name, ResumeSkill, "name")
        if name is None:
            continue
        normalized_name = normalize_skill(name)
        if (normalized_name, source, project_id) in seen:
            continue
        seen.add((normalized_name, source, project_id))
        skills.append(ResumeSkill(
            id=uuid.uuid4(),
            **owner,
            name=name,
            normalized_name=normalized_name,
            source=source,
            source_project_id=project_id,
            position=position,
        ))
    return skills


def build_children(resume: Resume) -> list[Base]:
    """Unsaved child rows for one résumé. position is the entry's index in its section of
    confirmed_data; entries the table's CHECK constraints would reject are skipped."""
    data = ResumeClassification.model_validate(resume.confirmed_data)
    owner = {"resume_id": resume.id, "user_id": resume.user_id}
    projects = [row for i, e in enumerate(data.projects) if (row := _project(e, i, owner)) is not None]
    rows: list[Base | None] = [
        *(_experience(e, "work", i, owner) for i, e in enumerate(data.work_experience)),
        *(_experience(e, "research", i, owner) for i, e in enumerate(data.research_experience)),
        *(_experience(e, "leadership", i, owner) for i, e in enumerate(data.leadership_activities)),
        *(_education(e, i, owner) for i, e in enumerate(data.education)),
        *projects,
        *(_achievement(e, "certification", i, owner) for i, e in enumerate(data.certifications)),
        *(_achievement(e, "award", i, owner) for i, e in enumerate(data.awards_honors)),
        # After the projects, so each skill's source_project_id is already in the list.
        *_skills(data.technical_skills, projects, owner),
    ]
    return [row for row in rows if row is not None]


# Skills first: they reference projects.
CHILD_MODELS = (ResumeSkill, ResumeProject, ResumeExperience, ResumeEducation, ResumeAchievement)


def rebuild_children(db: Session, resume: Resume) -> list[Base]:
    """Replace the résumé's child rows with ones built from its confirmed_data and return them. Safe
    to run again; the caller commits, so the rows are saved in the same transaction as the résumé."""
    rows = build_children(resume)
    for model in CHILD_MODELS:
        db.execute(delete(model).where(model.resume_id == resume.id))
    db.add_all(rows)
    return rows
