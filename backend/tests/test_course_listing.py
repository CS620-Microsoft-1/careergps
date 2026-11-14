"""Which school courses are listed: last taught within the last four fall/spring semesters."""
from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services import catalog_store, course_listing, uw_courses
from app.services.course_listing import is_listed, parse_term, recent_cutoff
from app.services.resources import resources_for


class TermTests(unittest.TestCase):
    def test_parses_guide_terms(self) -> None:
        self.assertEqual((2025, 3), parse_term("Fall 2025"))
        self.assertEqual((2026, 1), parse_term("spring 2026"))
        self.assertEqual((2026, 2), parse_term("Summer 2026"))
        self.assertIsNone(parse_term(None))
        self.assertIsNone(parse_term("Not yet taught"))

    def test_window_is_the_last_four_fall_and_spring_semesters(self) -> None:
        # Fall 2026: Fall 2026, Spring 2026, Fall 2025, Spring 2025.
        self.assertEqual(parse_term("Spring 2025"), recent_cutoff(date(2026, 11, 8)))
        # Spring 2027: Spring 2027, Fall 2026, Spring 2026, Fall 2025.
        self.assertEqual(parse_term("Fall 2025"), recent_cutoff(date(2027, 1, 20)))
        # Summer counts as the spring just finished.
        self.assertEqual(parse_term("Fall 2024"), recent_cutoff(date(2026, 7, 1)))


class IsListedTests(unittest.TestCase):
    NOV_2026 = date(2026, 11, 8)

    def listed(self, **entry) -> bool:
        return is_listed(entry, self.NOV_2026)

    def test_recently_taught_courses_are_listed(self) -> None:
        for term in ("Fall 2026", "Spring 2025", "Summer 2025"):
            self.assertTrue(self.listed(course_code="COMP SCI 400", last_taught=term), term)

    def test_courses_not_taught_recently_are_hidden(self) -> None:
        for term in ("Fall 2024", "Spring 2022"):
            self.assertFalse(self.listed(course_code="COMP SCI 400", last_taught=term), term)

    def test_graduate_courses_are_listed(self) -> None:
        self.assertTrue(self.listed(course_code="COMP SCI/E C E 760", last_taught="Fall 2026"))

    def test_courses_without_guide_details_are_listed(self) -> None:
        self.assertTrue(self.listed())
        self.assertTrue(self.listed(course_code="COMP SCI 440", last_taught=None))

    def test_resources_for_leaves_out_hidden_courses(self) -> None:
        def course(course_id, **details):
            return {"id": course_id, "type": "school_course", "title": course_id, "provider": "UW", "meta": "",
                    "description": "", "skills": ["sql"], "school": "University of Wisconsin–Madison", **details}

        courses = (course("recent", course_code="COMP SCI 564", last_taught="Fall 2026"),
                   course("stale", course_code="COMP SCI 565", last_taught="Spring 2020"),
                   course("graduate", course_code="COMP SCI 764", last_taught="Fall 2026"),
                   course("by-hand"))
        snapshot = replace(catalog_store.get_snapshot(), school_courses=courses)
        with patch.object(catalog_store, "get_snapshot", return_value=snapshot), \
             patch.object(course_listing, "reference_date", return_value=self.NOV_2026):
            ids = {entry["id"] for entry in resources_for("data_analyst", "UW–Madison")}
        self.assertEqual({"recent", "graduate", "by-hand"}, ids & {"recent", "stale", "graduate", "by-hand"})


class ReferenceDateTests(unittest.TestCase):
    """The window is counted back from the course guide snapshot, so it doesn't move until a refresh."""

    def test_shipped_data_has_a_snapshot_date(self) -> None:
        self.assertEqual(date(2026, 10, 13), uw_courses.snapshot_date())
        self.assertEqual(date(2026, 10, 13), course_listing.reference_date())

    def test_a_course_stays_listed_however_old_the_snapshot_gets(self) -> None:
        course = {"course_code": "COMP SCI 400", "last_taught": "Fall 2026"}
        with patch.object(uw_courses, "snapshot_date", return_value=date(2026, 10, 13)):
            self.assertTrue(is_listed(course))
        # Counted from a day three years later instead, the same course would be hidden.
        self.assertFalse(is_listed(course, date(2029, 9, 15)))

    def test_falls_back_to_today_without_a_snapshot(self) -> None:
        with patch.object(uw_courses, "snapshot_date", return_value=None):
            self.assertEqual(date.today(), course_listing.reference_date())

    def test_snapshot_date_is_the_oldest_subject_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "comp_sci.json").write_text('{"retrieved": "2027-02-01", "courses": []}', encoding="utf-8")
            Path(folder, "stat.json").write_text('{"retrieved": "2026-10-13", "courses": []}', encoding="utf-8")
            Path(folder, "math.json").write_text('{"retrieved": "not a date", "courses": []}', encoding="utf-8")
            subjects = {"comp_sci": ("COMP SCI", "uw-cs"), "stat": ("STAT", "uw-stat"), "math": ("MATH", "uw-math"),
                        "missing": ("E C E", "uw-ece")}
            with patch.object(uw_courses, "DATA_DIR", Path(folder)), patch.object(uw_courses, "SUBJECTS", subjects):
                uw_courses.snapshot_date.cache_clear()
                self.addCleanup(uw_courses.snapshot_date.cache_clear)
                self.assertEqual(date(2026, 10, 13), uw_courses.snapshot_date())
        with tempfile.TemporaryDirectory() as folder, patch.object(uw_courses, "DATA_DIR", Path(folder)):
            uw_courses.snapshot_date.cache_clear()
            self.assertIsNone(uw_courses.snapshot_date())


if __name__ == "__main__":
    unittest.main()
