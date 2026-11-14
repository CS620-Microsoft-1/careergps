"""UW–Madison course guide data: parsing a saved guide page, the tag checks, the catalog entries
and the course columns in the catalog write rules. No network, no database, no model calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services import catalog_writes, uw_courses
from scripts import tag_uw_courses
from scripts.parse_uw_guide import parse, title_case

PAGE = """<html><body>
<a href="https://web.archive.org/web/20261013201614/https://guide.wisc.edu/courses/comp_sci/">x</a>
<div class="sc_sccoursedescs"><div class="courseblock">
<p class="courseblocktitle noindent"><strong><span class="courseblockcode">COMP&nbsp;SCI/​E&nbsp;C&nbsp;E&nbsp;&nbsp;552</span> — INTRODUCTION TO COMPUTER ARCHITECTURE</strong></p>
<p class="courseblockcredits">1-3 credits.</p>
<p class="courseblockdesc noindent">
The design of computer systems and components.<br>
Processor design &amp; caches.</p>
<div class="cb-extras"><p class="courseblockextra"><span><strong>Requisites: </strong></span><span>COMP SCI 354</span></p>
<p class="courseblockextra"><span><strong>Last Taught: </strong></span><span class="cbextra-data">Spring 2026</span></p></div>
</div><div class="courseblock">
<p class="courseblocktitle noindent"><strong><span class="courseblockcode">COMP&nbsp;SCI&nbsp;440</span> — ARTIFICIAL INTELLIGENCE (AI) PARADIGMS TO PRACTICE</strong></p>
<p class="courseblockcredits">1 credit.</p>
<p class="courseblockdesc noindent">New course.</p>
</div></div></body></html>"""


class ParseGuideTests(unittest.TestCase):
    def test_reads_each_course_block_without_requisites(self) -> None:
        parsed = parse(PAGE)
        self.assertEqual("2026-10-13", parsed["snapshot_date"])
        first, second = parsed["courses"]
        self.assertEqual({"number": "552", "course_code": "COMP SCI/E C E 552", "title": "Introduction to Computer Architecture",
                          "credits": "1-3", "description": "The design of computer systems and components. Processor design & caches.",
                          "last_taught": "Spring 2026"}, first)
        self.assertNotIn("354", json.dumps(parsed))
        self.assertEqual(("440", "1", None), (second["number"], second["credits"], second["last_taught"]))

    def test_title_case(self) -> None:
        self.assertEqual("Artificial Intelligence (AI) Paradigms to Practice",
                         title_case("ARTIFICIAL INTELLIGENCE (AI) PARADIGMS TO PRACTICE"))
        self.assertEqual("Database Management Systems: Design and Implementation",
                         title_case("DATABASE MANAGEMENT SYSTEMS: DESIGN AND IMPLEMENTATION"))
        self.assertEqual("Human-Computer Interaction", title_case("HUMAN-COMPUTER INTERACTION"))
        self.assertEqual("Programming III", title_case("PROGRAMMING III"))


class TagCheckTests(unittest.TestCase):
    def test_keeps_known_skills_and_reports_problems(self) -> None:
        courses = [{"number": "564", "description": "Relational  database design and SQL."},
                   {"number": "698", "description": "Directed study."},
                   {"number": "400", "description": "Java."}]
        answer = {"courses": [
            {"number": "564", "skill_ids": ["sql", "relational_sql", "made_up"], "quote": "database design and SQL"},
            {"number": "698", "skill_ids": [], "quote": ""},
            {"number": "999", "skill_ids": ["sql"], "quote": ""},
        ]}
        tags, problems = tag_uw_courses.check(answer, courses, {"sql", "relational_sql"})
        self.assertEqual({"564": {"skills": ["sql", "relational_sql"], "quote": "database design and SQL"},
                          "698": {"skills": [], "quote": ""}}, tags)
        self.assertEqual(3, len(problems))
        self.assertTrue(any("made_up" in problem for problem in problems))
        self.assertTrue(any(problem.startswith("400") for problem in problems))

    def test_rejects_quotes_not_in_the_description(self) -> None:
        _, problems = tag_uw_courses.check(
            {"courses": [{"number": "564", "skill_ids": ["sql"], "quote": "teaches NoSQL"}]},
            [{"number": "564", "description": "Relational databases."}], {"sql"})
        self.assertEqual(1, len(problems))

    def test_prompt_lists_every_core_skill_and_no_requisites(self) -> None:
        table, known = tag_uw_courses.skill_table()
        self.assertEqual(60, len(known))
        text = tag_uw_courses.prompt([{"number": "564", "course_code": "COMP SCI 564", "title": "DBMS",
                                       "description": "Relational databases.", "last_taught": "Fall 2026"}], table)
        self.assertIn("relational_sql | SQL & relational databases | software engineer", text)
        self.assertNotIn("Fall 2026", text)


class CourseEntriesTests(unittest.TestCase):
    def entries(self, courses, tags):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "comp_sci.json").write_text(json.dumps({"courses": courses}))
            (Path(directory) / "comp_sci_skills.json").write_text(json.dumps(tags))
            with patch.object(uw_courses, "DATA_DIR", Path(directory)):
                return uw_courses.course_entries()

    def test_every_course_becomes_a_school_course_entry(self) -> None:
        course = {"number": "564", "course_code": "COMP SCI 564", "title": "Database Management Systems",
                  "credits": "3", "description": "Relational databases.", "last_taught": "Fall 2026",
                  "url": "https://guide.wisc.edu/courses/comp_sci/"}
        untagged = {**course, "number": "698", "course_code": "COMP SCI 698"}
        entries = self.entries([course, untagged], {"564": {"skills": ["sql"], "quote": "x"}, "698": {"skills": []}})
        self.assertEqual([["sql"], []], [entry["skills"] for entry in entries])
        entry = entries[0]
        self.assertEqual(("uw-cs-564", "COMP SCI 564: Database Management Systems", "3 credits · Last taught Fall 2026"),
                         (entry["id"], entry["title"], entry["meta"]))
        # The catalog write rules accept the entry as it is.
        values = catalog_writes.school_resource_values("school_course", entry)
        self.assertEqual(("COMP SCI 564", "3", "Fall 2026"), (values["course_code"], values["credits"], values["last_taught"]))
        self.assertEqual([], catalog_writes.school_resource_values("school_course", entries[1])["skills"])

    def test_meta(self) -> None:
        self.assertEqual("1 credit", uw_courses.meta("1", None))
        self.assertEqual("1-3 credits · Last taught Spring 2025", uw_courses.meta("1-3", "Spring 2025"))

    def test_no_files_no_entries(self) -> None:
        with patch.object(uw_courses, "DATA_DIR", Path("/nonexistent")):
            self.assertEqual([], uw_courses.course_entries())

    def test_student_orgs_cannot_have_course_details(self) -> None:
        org = {"id": "club", "title": "Club", "provider": "UW", "meta": "", "description": "", "skills": ["sql"],
               "school": "UW", "course_code": "COMP SCI 1"}
        with self.assertRaises(ValueError):
            catalog_writes.school_resource_values("student_org", org)
        with self.assertRaises(ValueError):  # only courses may close no skill
            catalog_writes.school_resource_values("student_org", {**org, "course_code": None, "skills": []})


if __name__ == "__main__":
    unittest.main()
