"""Taken courses: the résumé course name match, the /me/courses API and the plan "done" hook.
No database: the student_courses storage functions are replaced with an in-memory dict
(tests/test_student_courses_postgres.py covers the real table)."""
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient

from app.api import deps
from app.core.security import SupabaseTokenVerifier
from app.main import app
from app.models import StudentCourse
from app.services import student_courses
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.student_courses import course_list_strings, match_courses
from tests.support import SUPABASE_URL, FakeJwks, make_token, new_signing_key
from tests.test_me import FakeAccountService, onboarding_body


def _named(number, name):
    return {"id": f"uw-cs-{number}", "course_code": f"COMP SCI {number}", "title": f"COMP SCI {number}: {name}"}


NAMED = [
    _named(300, "Programming II"),
    _named(320, "Data Science Programming II"),
    _named(532, "Matrix Methods in Machine Learning"),
    _named(537, "Introduction to Operating Systems"),
    _named(564, "Database Management Systems: Design and Implementation"),
    _named(566, "Introduction to Computer Vision"),
    _named(577, "Introduction to Algorithms"),
    _named(760, "Machine Learning"),
    _named(766, "Computer Vision"),
    _named(774, "Data Exploration, Cleaning, and Integration for Data Science"),
    {"id": "uw-stat-240", "course_code": None, "title": "STAT 240: Data Science Modeling I"},
]


class MatchCourseNamesTests(unittest.TestCase):
    def ids(self, *course_lists, courses=NAMED):
        return [course["id"] for course in match_courses(course_lists, courses)]

    def test_matches_names_however_they_are_punctuated(self) -> None:
        self.assertEqual(["uw-cs-537"], self.ids("Coursework: Introduction to Operating Systems"))
        self.assertEqual(["uw-cs-537"], self.ids("Relevant courses: operating systems; Calculus"))
        self.assertEqual(["uw-cs-537"], self.ids("Intro to Operating Systems"))
        self.assertEqual(["uw-cs-564"], self.ids("Database Management Systems"))
        self.assertEqual(["uw-cs-564"], self.ids("Database Management Systems: Design and Implementation"))
        self.assertEqual(["uw-cs-774"], self.ids("Data Exploration, Cleaning, and Integration for Data Science"))
        self.assertEqual(["uw-stat-240"], self.ids("Data Science Modeling I"))

    def test_names_are_whole_words_inside_one_list_item(self) -> None:
        self.assertEqual([], self.ids("Operating Systemsx", "Cooperating systems"))
        # "Machine" and "Learning Theory" are two list items, so "Machine Learning" isn't there.
        self.assertEqual([], self.ids("Statistical Machine, Learning Theory"))

    def test_a_one_word_name_must_be_the_whole_item(self) -> None:
        self.assertEqual(["uw-cs-577"], self.ids("Coursework: Algorithms, Linear Algebra"))
        self.assertEqual(["uw-cs-577"], self.ids("Coursework: Intro. to Algorithms, Linear Algebra"))
        self.assertEqual([], self.ids("Designed algorithms for route planning"))

    def test_the_longer_name_wins(self) -> None:
        self.assertEqual(["uw-cs-532"], self.ids("Matrix Methods in Machine Learning"))
        self.assertEqual(["uw-cs-320"], self.ids("Data Science Programming II"))
        self.assertEqual(["uw-cs-300", "uw-cs-760"], self.ids("Programming II, Machine Learning"))

    def test_a_shared_name_gives_the_lowest_numbered_course(self) -> None:
        self.assertEqual(["uw-cs-566"], self.ids("Computer Vision"))
        self.assertEqual(["uw-cs-566"], self.ids("Introduction to Computer Vision"))

    def test_names_count_only_in_course_lists(self) -> None:
        data = {"education": [{"institution": "UW", "major": "Machine Learning", "content": ["Operating Systems"]}],
                "technical_skills": ["Machine Learning", "Computer Vision"],
                "projects": [{"name": "Algorithms", "content": ["Used computer vision in CS 577"]}],
                "other": [{"content": "Relevant Coursework: Database Management Systems"}]}
        self.assertEqual(["Operating Systems", "Relevant Coursework: Database Management Systems"],
                         list(course_list_strings(data)))
        found = match_courses(course_list_strings(data), NAMED)
        # Not the names in the major, the skills or the project, and not the course code.
        self.assertEqual(["uw-cs-537", "uw-cs-564"], [course["id"] for course in found])
        self.assertEqual([], list(course_list_strings(None)))


class _TakenStore:
    """In-memory student_courses."""

    def __init__(self, known: set[str]) -> None:
        self.rows: dict[tuple[uuid.UUID, str], StudentCourse] = {}
        self.known = known
        self.universities: list[str | None] = []

    def list_taken(self, session, user_id):
        return [row for (owner, _), row in self.rows.items() if owner == user_id]

    def mark_taken(self, session, user_id, course_id, source, university):
        self.universities.append(university)
        if course_id not in self.known:
            raise KeyError(course_id)
        return self.rows.setdefault((user_id, course_id), StudentCourse(
            user_id=user_id, course_id=course_id, source=source, created_at=datetime.now(UTC)))

    def unmark_taken(self, session, user_id, course_id):
        self.rows.pop((user_id, course_id), None)


class TakenCoursesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        key = new_signing_key()
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(key))
        self.accounts = FakeAccountService()
        self.temp = tempfile.TemporaryDirectory()
        self.store = _TakenStore({"uw-cs-564", "uw-cs-400", "uw-cs-540"})
        self.session = MagicMock()
        app.dependency_overrides[deps.get_account_service] = lambda: self.accounts
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        app.dependency_overrides[deps.get_db] = lambda: self.session
        app.dependency_overrides[get_plan_store] = lambda: LocalPlanStore(Path(self.temp.name))
        for name in ("list_taken", "mark_taken", "unmark_taken"):
            patcher = patch.object(student_courses, name, getattr(self.store, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.user_id = uuid.uuid4()
        self.headers = {"Authorization": f"Bearer {make_token(key, sub=str(self.user_id), email='ada@example.com')}"}
        body = onboarding_body()
        body["resume"]["classification"]["education"][0]["content"] = ["Relevant coursework: Database Management Systems, Programming III"]
        self.assertEqual(201, self.client.post("/me", json=body, headers=self.headers).status_code)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.temp.cleanup()

    def taken(self):
        response = self.client.get("/me/courses", headers=self.headers)
        self.assertEqual(200, response.status_code, response.text)
        return [(course["course_id"], course["source"]) for course in response.json()["courses"]]

    def test_needs_login(self) -> None:
        self.assertEqual(401, self.client.get("/me/courses").status_code)
        self.assertEqual(401, self.client.put("/me/courses/uw-cs-564").status_code)

    def test_mark_and_unmark(self) -> None:
        self.assertEqual([], self.taken())
        marked = self.client.put("/me/courses/uw-cs-564", headers=self.headers)
        self.assertEqual(200, marked.status_code, marked.text)
        self.assertEqual("manual", marked.json()["source"])
        # Repeating keeps the first record.
        self.client.put("/me/courses/uw-cs-564", json={"source": "resume"}, headers=self.headers)
        self.assertEqual([("uw-cs-564", "manual")], self.taken())
        self.assertEqual(204, self.client.delete("/me/courses/uw-cs-564", headers=self.headers).status_code)
        self.assertEqual([], self.taken())

    def test_marking_passes_the_students_university(self) -> None:
        university = onboarding_body()["university"]
        self.client.put("/me/courses/uw-cs-564", headers=self.headers)
        self.client.put("/plan/items/uw-cs-564", json={"job_family": "data_analyst", "status": "done"},
                        headers=self.headers)
        self.assertEqual([university, university], self.store.universities)

    def test_unknown_course_or_source(self) -> None:
        self.assertEqual(404, self.client.put("/me/courses/not-a-course", headers=self.headers).status_code)
        self.assertEqual(422, self.client.put("/me/courses/uw-cs-564", json={"source": "plan"},
                                              headers=self.headers).status_code)

    def test_resume_matches_skip_taken_courses(self) -> None:
        def matches():
            response = self.client.get("/me/courses/resume-matches?job_family=data_analyst", headers=self.headers)
            self.assertEqual(200, response.status_code, response.text)
            return response.json()["course_ids"]

        # Programming III (COMP SCI 400) closes no data analyst skill, so only COMP SCI 564 is listed for this role.
        self.assertEqual(["uw-cs-564"], matches())
        self.client.put("/me/courses/uw-cs-564", json={"source": "resume"}, headers=self.headers)
        self.assertEqual([], matches())
        self.assertEqual([("uw-cs-564", "resume")], self.taken())

    def test_plan_done_records_a_taken_course_one_way(self) -> None:
        def put(resource_id, status):
            response = self.client.put(f"/plan/items/{resource_id}", json={"job_family": "data_analyst",
                                       "status": status}, headers=self.headers)
            self.assertEqual(200, response.status_code, response.text)

        put("uw-cs-564", "saved")
        put("sqlbolt", "done")
        self.assertEqual([], self.taken())
        put("uw-cs-564", "done")
        self.assertEqual([("uw-cs-564", "plan")], self.taken())
        put("uw-cs-564", "saved")
        self.assertEqual([("uw-cs-564", "plan")], self.taken())

    def test_plan_done_still_saves_when_recording_fails(self) -> None:
        self.store.known.clear()
        response = self.client.put("/plan/items/uw-cs-564", json={"job_family": "data_analyst", "status": "done"},
                                   headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual("done", response.json()["status"])
        self.session.rollback.assert_called()


if __name__ == "__main__":
    unittest.main()
