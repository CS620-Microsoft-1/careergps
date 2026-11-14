"""Taken courses: the résumé course-code match, the /me/courses API and the plan "done" hook.
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
from app.services.student_courses import match_courses, resume_strings
from tests.support import SUPABASE_URL, FakeJwks, make_token, new_signing_key
from tests.test_me import FakeAccountService, onboarding_body


def _course(course_id, code=None, title=None):
    return {"id": course_id, "course_code": code, "title": title or f"{code}: A course"}


COURSES = [
    _course("uw-cs-400", "COMP SCI 400"),
    _course("uw-cs-540", "COMP SCI 540"),
    _course("uw-cs-552", "COMP SCI/E C E 552"),
    _course("uw-cs-577", "COMP SCI 577"),
    _course("uw-stat-240", title="STAT 240: Data Science Modeling I"),
]


class MatchCoursesTests(unittest.TestCase):
    def ids(self, *texts):
        return [course["id"] for course in match_courses(texts, COURSES)]

    def test_matches_the_ways_students_write_codes(self) -> None:
        self.assertEqual(["uw-cs-400"], self.ids("Relevant coursework: COMP SCI 400"))
        self.assertEqual(["uw-cs-400"], self.ids("CS400 (Programming III)"))
        self.assertEqual(["uw-cs-400"], self.ids("Comp. Sci. 400"))
        self.assertEqual(["uw-cs-400"], self.ids("compsci 400"))
        self.assertEqual(["uw-cs-552"], self.ids("ECE 552 Computer Architecture"))
        self.assertEqual(["uw-stat-240"], self.ids("Stat 240"))

    def test_matches_lists_after_one_subject(self) -> None:
        self.assertEqual(["uw-cs-400", "uw-cs-540", "uw-cs-577"], self.ids("CS 400, 540 and 577"))
        self.assertEqual(["uw-cs-400", "uw-cs-540"], self.ids("COMP SCI 540/400"))

    def test_ignores_other_numbers_and_words(self) -> None:
        self.assertEqual([], self.ids("GPA 3.400", "Class of 2027", "Physics 400", "CS 4000", "ABCS 400"))
        self.assertEqual([], self.ids("CS 999"))

    def test_reads_every_string_in_the_resume(self) -> None:
        data = {"education": [{"school": "UW", "content": ["Coursework: CS 577"]}], "skills": ["Python"],
                "projects": [{"content": ["Built a compiler for COMP SCI 536"]}], "gpa": 3.9}
        self.assertEqual(["uw-cs-577"], [c["id"] for c in match_courses(resume_strings(data), COURSES)])


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
        body["resume"]["classification"]["education"][0]["content"] = ["Relevant coursework: CS 564, COMP SCI 400"]
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

        # COMP SCI 400 closes no data analyst skill, so only CS 564 is listed for this role.
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
