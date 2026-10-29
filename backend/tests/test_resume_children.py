"""Rules for the résumé child tables that don't need a database."""
import copy
import json
import os
import sys
import unittest
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# CI has no .env; creating the engine doesn't connect, so a dummy URL is enough.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test")

from pydantic import ValidationError

from app.models import (
    Resume,
    ResumeAchievement,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    ResumeSkill,
)
from app.services.resume_children import (
    EDUCATION_END_MONTH,
    EXPERIENCE_END_MONTH,
    START_MONTH,
    _clean_lines,
    _fit_text,
    _fit_url,
    CHILD_MODELS,
    build_children,
    is_current,
    normalize_skill,
    parse_degree_level,
    parse_gpa,
    parse_month,
    rebuild_children,
)

EXAMPLE = json.loads((BACKEND_ROOT.parent / "docs" / "resume-classification-example.json").read_text(encoding="utf-8"))

EMPTY_SECTIONS = {
    key: [] for key in (
        "research_interests", "education", "work_experience", "research_experience", "projects",
        "technical_skills", "languages", "publications", "awards_honors", "certifications",
        "leadership_activities", "other",
    )
}


def _dated(**fields) -> dict:
    return {"start_date": None, "end_date": None, "location": None, "content": [], **fields}


def work(**fields) -> dict:
    return _dated(**{"company": None, "title": None, **fields})


def research(**fields) -> dict:
    return _dated(**{"organization": None, "title": None, **fields})


def leadership(**fields) -> dict:
    return _dated(**{"organization": None, "role": None, **fields})


def resume_with(**sections) -> Resume:
    data = {"personal_information": copy.deepcopy(EXAMPLE["personal_information"]), **EMPTY_SECTIONS, **sections}
    return Resume(id=uuid.uuid4(), user_id=uuid.uuid4(), confirmed_data=data)


def rows_of(rows: list, model: type) -> list:
    return [row for row in rows if isinstance(row, model)]


class ValueFittingTests(unittest.TestCase):
    def test_text_is_trimmed_cut_to_the_column_and_blank_becomes_none(self) -> None:
        self.assertEqual("Google", _fit_text("  Google  ", ResumeExperience, "organization"))
        self.assertEqual(255, len(_fit_text("x" * 300, ResumeExperience, "organization")))
        self.assertIsNone(_fit_text("   ", ResumeExperience, "organization"))
        self.assertIsNone(_fit_text(None, ResumeExperience, "organization"))

    def test_a_url_too_long_for_its_column_is_dropped_not_cut(self) -> None:
        self.assertEqual("https://a.dev", _fit_url(" https://a.dev ", ResumeProject, "url"))
        self.assertIsNone(_fit_url("https://a.dev/" + "x" * 2048, ResumeProject, "url"))
        self.assertIsNone(_fit_url("", ResumeProject, "url"))

    def test_empty_bullet_points_are_removed(self) -> None:
        self.assertEqual(["Built X", "Led Y"], _clean_lines(["  Built X ", "", "   ", "Led Y"]))


class ParseMonthTests(unittest.TestCase):
    def test_month_formats(self) -> None:
        for text in ("2024-05", "2024-5", "05/2024", "May 2024", "may 2024"):
            with self.subTest(text=text):
                self.assertEqual((date(2024, 5, 1), "month"), parse_month(text, START_MONTH))
        for text in ("Sep 2024", "Sept. 2024", "September, 2024"):
            with self.subTest(text=text):
                self.assertEqual((date(2024, 9, 1), "month"), parse_month(text, START_MONTH))

    def test_year_only_uses_the_given_month(self) -> None:
        self.assertEqual((date(2022, 1, 1), "year"), parse_month("2022", START_MONTH))
        self.assertEqual((date(2022, 12, 1), "year"), parse_month("2022", EXPERIENCE_END_MONTH))
        self.assertEqual((date(2022, 5, 1), "year"), parse_month("2022", EDUCATION_END_MONTH))

    def test_anything_else_is_null_never_a_guess(self) -> None:
        for text in (None, "", "Present", "Spring 2023", "2024-13", "13/2024", "Mayo 2024", "1850", "2024-05-17"):
            with self.subTest(text=text):
                self.assertEqual((None, None), parse_month(text, START_MONTH))


class SmallParserTests(unittest.TestCase):
    def test_current_end_dates(self) -> None:
        for text in ("Present", " present ", "Current", "NOW"):
            self.assertTrue(is_current(text), text)
        for text in (None, "", "2024", "Presently"):
            self.assertFalse(is_current(text), text)

    def test_degree_level(self) -> None:
        cases = {
            "B.S.": "bachelor",
            "Bachelor of Science in Computer Science": "bachelor",
            "BA": "bachelor",
            "M.S.": "master",
            "Master of Science": "master",
            "MBA": "master",
            "Ph.D.": "doctorate",
            "Doctor of Philosophy": "doctorate",
            "Associate of Arts": "associate",
            "High School Diploma": "other",
        }
        for degree, level in cases.items():
            with self.subTest(degree=degree):
                self.assertEqual(level, parse_degree_level(degree))
        self.assertIsNone(parse_degree_level(None))
        self.assertIsNone(parse_degree_level("  "))

    def test_gpa(self) -> None:
        self.assertEqual((Decimal("3.80"), Decimal("4.00")), parse_gpa("3.8/4.0"))
        self.assertEqual((Decimal("3.80"), Decimal("4.00")), parse_gpa("GPA: 3.8 / 4"))
        self.assertEqual((Decimal("3.80"), None), parse_gpa("3.8"))
        self.assertEqual((Decimal("3.80"), None), parse_gpa("3.8/0"))
        self.assertEqual((None, None), parse_gpa("N/A"))
        self.assertEqual((None, None), parse_gpa(None))
        self.assertEqual((None, None), parse_gpa("12345"))

    def test_normalize_skill(self) -> None:
        self.assertEqual("postgresql", normalize_skill("  PostgreSQL "))
        self.assertEqual("node.js", normalize_skill("Node.js"))
        self.assertEqual("machine learning", normalize_skill("Machine   Learning"))
        # NFKC turns full-width letters into ordinary ones.
        self.assertEqual("python", normalize_skill("Ｐｙｔｈｏｎ"))
        self.assertEqual(100, len(normalize_skill("x" * 150)))


class BuildChildrenTests(unittest.TestCase):
    def test_example_resume(self) -> None:
        resume = Resume(id=uuid.uuid4(), user_id=uuid.uuid4(), confirmed_data=copy.deepcopy(EXAMPLE))
        rows = build_children(resume)

        work = rows_of(rows, ResumeExperience)
        self.assertEqual([("work", 0), ("work", 1)], [(row.kind, row.position) for row in work])
        self.assertEqual(EXAMPLE["work_experience"][0]["company"], work[0].organization)
        self.assertEqual(EXAMPLE["work_experience"][0]["content"], work[0].content)
        # "2022" to "Present"
        self.assertEqual((date(2022, 1, 1), None, "year", True),
                         (work[0].start_month, work[0].end_month, work[0].date_precision, work[0].is_current))
        # "2019" to "2022": a year-only end uses December.
        self.assertEqual((date(2019, 1, 1), date(2022, 12, 1), False),
                         (work[1].start_month, work[1].end_month, work[1].is_current))

        [education] = rows_of(rows, ResumeEducation)
        self.assertEqual("bachelor", education.degree_level)
        # A year-only graduation uses May.
        self.assertEqual((None, date(2014, 5, 1), "year"),
                         (education.start_month, education.end_month, education.date_precision))
        self.assertEqual(1, len(rows_of(rows, ResumeProject)))
        self.assertEqual([], rows_of(rows, ResumeAchievement))

        for row in rows:
            self.assertEqual((resume.id, resume.user_id), (row.resume_id, row.user_id))
        self.assertEqual(len(rows), len({row.id for row in rows}))

    def test_each_section_maps_to_its_table_and_kind(self) -> None:
        rows = build_children(resume_with(
            work_experience=[work(company="Acme", title="Engineer")],
            research_experience=[research(organization="UW Lab", title="Research Assistant")],
            leadership_activities=[leadership(organization="ACM", role="President")],
            certifications=[{"name": "AWS SAA", "issuer": "Amazon", "date": "May 2024",
                             "url": "https://aws.example/cert", "content": []}],
            awards_honors=[{"name": "Dean's List", "issuer": "UW", "date": "2023", "content": []}],
        ))

        experiences = {row.kind: (row.organization, row.title) for row in rows_of(rows, ResumeExperience)}
        self.assertEqual({"work": ("Acme", "Engineer"), "research": ("UW Lab", "Research Assistant"),
                          "leadership": ("ACM", "President")}, experiences)

        certification, award = rows_of(rows, ResumeAchievement)
        self.assertEqual(("certification", "https://aws.example/cert", date(2024, 5, 1), "month"),
                         (certification.kind, certification.url, certification.issued_month,
                          certification.date_precision))
        self.assertEqual(("award", None, "2023", date(2023, 1, 1), "year"),
                         (award.kind, award.url, award.issued_date, award.issued_month, award.date_precision))

    def test_position_is_the_index_in_its_own_section(self) -> None:
        rows = build_children(resume_with(
            work_experience=[work(company="A"), work(company="B")],
            research_experience=[research(organization="Lab")],
        ))
        self.assertEqual([("work", 0, "A"), ("work", 1, "B"), ("research", 0, "Lab")],
                         [(row.kind, row.position, row.organization) for row in rows])

    def test_entries_the_constraints_would_reject_are_skipped_but_keep_their_position(self) -> None:
        blank_experience = work(company="  ", content=["", " "])
        rows = build_children(resume_with(
            work_experience=[blank_experience, work(company="Acme")],
            education=[{"institution": None, "degree": None, "major": None, "start_date": None,
                        "end_date": "2024", "gpa": "3.9", "content": ["Coursework"]}],
            projects=[{"name": None, "url": "https://x.dev", "technologies": ["Go"], "content": []}],
            certifications=[{"name": " ", "issuer": "Amazon", "date": None, "url": None, "content": []}],
        ))
        self.assertEqual([("work", 1)], [(row.kind, row.position) for row in rows])

    def test_values_are_cleaned_and_fitted(self) -> None:
        rows = build_children(resume_with(
            projects=[{"name": "  CareerGPS ", "url": "https://x.dev/" + "y" * 3000,
                       "technologies": [" Python ", ""], "content": ["Built it", "  "]}],
            education=[{"institution": "UW", "degree": "M.S.", "major": "CS", "start_date": "2023-09",
                        "end_date": "2025-05", "gpa": "3.9/4.0", "content": []}],
        ))
        [project] = rows_of(rows, ResumeProject)
        self.assertEqual(("CareerGPS", None, ["Python"], ["Built it"]),
                         (project.name, project.url, project.technologies, project.content))
        [education] = rows_of(rows, ResumeEducation)
        self.assertEqual(("master", Decimal("3.90"), Decimal("4.00"), date(2023, 9, 1), date(2025, 5, 1), "month"),
                         (education.degree_level, education.gpa_value, education.gpa_scale,
                          education.start_month, education.end_month, education.date_precision))

    def test_invalid_confirmed_data_fails_loudly(self) -> None:
        resume = resume_with()
        del resume.confirmed_data["projects"]
        with self.assertRaises(ValidationError):
            build_children(resume)



def project(name, technologies, content=()) -> dict:
    return {"name": name, "url": None, "technologies": list(technologies), "content": list(content)}


class SkillRowTests(unittest.TestCase):
    def skills(self, **sections) -> tuple[list[ResumeSkill], list[ResumeProject]]:
        rows = build_children(resume_with(**sections))
        return rows_of(rows, ResumeSkill), rows_of(rows, ResumeProject)

    def test_listed_skills_keep_their_order(self) -> None:
        skills, _ = self.skills(technical_skills=["Python", " PostgreSQL ", "React"])
        self.assertEqual(
            [("Python", "python", "listed", 0, None), ("PostgreSQL", "postgresql", "listed", 1, None),
             ("React", "react", "listed", 2, None)],
            [(s.name, s.normalized_name, s.source, s.position, s.source_project_id) for s in skills],
        )

    def test_project_skills_link_to_their_project(self) -> None:
        skills, projects = self.skills(projects=[project("CareerGPS", ["FastAPI", "Python"]),
                                                 project("Bot", ["Go"])])
        career_gps, bot = projects
        self.assertEqual(
            [("fastapi", career_gps.id), ("python", career_gps.id), ("go", bot.id)],
            [(s.normalized_name, s.source_project_id) for s in skills],
        )
        self.assertTrue(all(s.source == "project" and s.position is None for s in skills))

    def test_the_same_skill_in_different_places_is_separate_evidence(self) -> None:
        skills, projects = self.skills(
            technical_skills=["Python"],
            projects=[project("A", ["Python"]), project("B", ["python"])],
        )
        self.assertEqual(
            [("listed", None), ("project", projects[0].id), ("project", projects[1].id)],
            [(s.source, s.source_project_id) for s in skills],
        )

    def test_duplicates_in_one_place_keep_the_first_spelling(self) -> None:
        skills, _ = self.skills(
            technical_skills=["Python", "SQL", "python ", "PYTHON"],
            projects=[project("A", ["Go", "go"])],
        )
        self.assertEqual(
            [("Python", "listed", 0), ("SQL", "listed", 1), ("Go", "project", None)],
            [(s.name, s.source, s.position) for s in skills],
        )

    def test_blank_and_long_names(self) -> None:
        skills, _ = self.skills(technical_skills=["", "   ", "x" * 150])
        [skill] = skills
        self.assertEqual((100, 100, 2), (len(skill.name), len(skill.normalized_name), skill.position))

    def test_a_skipped_project_gives_no_skills(self) -> None:
        skills, projects = self.skills(projects=[project(None, ["Rust"]), project("Kept", ["Go"])])
        self.assertEqual(["Kept"], [p.name for p in projects])
        self.assertEqual(["go"], [s.normalized_name for s in skills])

    def test_skills_come_after_the_projects_they_reference(self) -> None:
        rows = build_children(resume_with(projects=[project("A", ["Go"])]))
        self.assertLess(
            next(i for i, row in enumerate(rows) if isinstance(row, ResumeProject)),
            next(i for i, row in enumerate(rows) if isinstance(row, ResumeSkill)),
        )



class RebuildChildrenTests(unittest.TestCase):
    def test_deletes_the_old_rows_then_adds_the_new_ones_without_committing(self) -> None:
        db = mock.Mock()
        resume = resume_with(technical_skills=["Python"], projects=[project("A", ["Go"])])

        rebuild_children(db, resume)

        deleted = [call.args[0].table.name for call in db.execute.call_args_list]
        self.assertEqual([model.__tablename__ for model in CHILD_MODELS], deleted)
        self.assertEqual("resume_skills", deleted[0])  # skills reference projects
        [rows] = db.add_all.call_args.args
        self.assertEqual(["ResumeProject", "ResumeSkill", "ResumeSkill"], [type(row).__name__ for row in rows])
        db.commit.assert_not_called()

    def test_invalid_data_changes_nothing(self) -> None:
        db = mock.Mock()
        resume = resume_with()
        del resume.confirmed_data["projects"]

        with self.assertRaises(ValidationError):
            rebuild_children(db, resume)
        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
