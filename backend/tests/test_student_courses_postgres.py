"""Course details and student_courses against a real, throwaway Postgres with the real migrations.

Skipped unless CGPS_TEST_DATABASE_URL is set, so CI (no database) skips it. Never point it at the
shared Supabase database: it drops and recreates the public and auth schemas. For example:

    CGPS_TEST_DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5433/scratch_db \
        python -m unittest tests.test_student_courses_postgres
"""
import os
import subprocess
import sys
import unittest
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import BACKEND_ROOT
from app.services import catalog_store, catalog_writes, student_courses
from app.services.catalog_store import DatabaseCatalogSource, FileCatalogSource

DATABASE_URL = os.environ.get("CGPS_TEST_DATABASE_URL")
UW = "University of Wisconsin–Madison"
COURSE = {"id": "uw-cs-564", "title": "COMP SCI 564: Database Management Systems", "provider": "UW–Madison course",
          "meta": "3 credits · Last taught Fall 2026", "description": "Relational databases.", "skills": ["sql"],
          "school": "University of Wisconsin–Madison", "course_code": "COMP SCI 564", "credits": "3",
          "last_taught": "Fall 2026"}


@unittest.skipUnless(DATABASE_URL, "set CGPS_TEST_DATABASE_URL to a throwaway local Postgres to run")
class StudentCoursesPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if "supabase" in DATABASE_URL:
            raise RuntimeError("CGPS_TEST_DATABASE_URL points at Supabase; use a throwaway local database")
        cls.engine = create_engine(DATABASE_URL)
        with cls.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public"))
            # Stand-in for Supabase's auth schema: only what the migrations touch.
            connection.execute(text("DROP SCHEMA IF EXISTS auth CASCADE; CREATE SCHEMA auth"))
            connection.execute(text("CREATE TABLE auth.users (id uuid PRIMARY KEY, created_at timestamptz"
                                    " NOT NULL DEFAULT now(), email_confirmed_at timestamptz)"))
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, check=True,
                       capture_output=True,
                       env={**os.environ, "DATABASE_URL": DATABASE_URL, "MIGRATION_DATABASE_URL": DATABASE_URL})
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE student_courses, users, auth.users, school_courses CASCADE"))
        self.user_id = self.add_user()
        with self.Session() as session:
            catalog_writes.upsert_school_course(session, COURSE)
            session.commit()

    def tearDown(self) -> None:
        catalog_store.use_source(FileCatalogSource())

    def add_user(self) -> uuid.UUID:
        user_id = uuid.uuid4()
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": user_id})
            connection.execute(text(
                "INSERT INTO users (id, primary_email, first_name, last_name, target_role, experience_level,"
                " graduation_year, university, preferred_location, terms_accepted_at) VALUES (:id, :email, 'Ada',"
                " 'Lovelace', 'Data Analyst', 'Internship', 2027, 'University of Wisconsin–Madison', 'Madison, WI',"
                " now())"), {"id": user_id, "email": f"{user_id}@example.com"})
        return user_id

    def taken(self, user_id=None):
        with self.Session() as session:
            return [(row.course_id, row.source) for row in student_courses.list_taken(session, user_id or self.user_id)]

    def test_course_details_round_trip_through_the_catalog(self) -> None:
        catalog_store.use_source(DatabaseCatalogSource(self.Session))
        entry = {course["id"]: course for course in catalog_store.get_snapshot().school_courses}["uw-cs-564"]
        self.assertEqual(("COMP SCI 564", "3", "Fall 2026"), (entry["course_code"], entry["credits"], entry["last_taught"]))
        with self.Session() as session:
            self.assertEqual("unchanged", catalog_writes.upsert_school_course(session, COURSE))

    def test_mark_keeps_the_first_record_and_unmark_deletes_it(self) -> None:
        with self.Session() as session:
            student_courses.mark_taken(session, self.user_id, "uw-cs-564", "resume", UW)
            student_courses.mark_taken(session, self.user_id, "uw-cs-564", "manual", UW)
        self.assertEqual([("uw-cs-564", "resume")], self.taken())
        self.assertEqual([], self.taken(self.add_user()))
        with self.Session() as session:
            student_courses.unmark_taken(session, self.user_id, "uw-cs-564")
            student_courses.unmark_taken(session, self.user_id, "uw-cs-564")
        self.assertEqual([], self.taken())

    def test_unknown_courses_are_refused(self) -> None:
        with self.Session() as session, self.assertRaises(KeyError):
            student_courses.mark_taken(session, self.user_id, "uw-cs-000", "manual", UW)

    def test_courses_of_another_school_are_refused(self) -> None:
        with self.Session() as session:
            for university in ("Northlake University", None, ""):
                with self.assertRaises(KeyError):
                    student_courses.mark_taken(session, self.user_id, "uw-cs-564", "manual", university)
            # Another spelling of the same school is accepted.
            student_courses.mark_taken(session, self.user_id, "uw-cs-564", "manual", "UW-Madison")
        self.assertEqual([("uw-cs-564", "manual")], self.taken())

    def test_inactive_courses_can_still_be_marked(self) -> None:
        with self.Session() as session:
            catalog_writes.deactivate(session, "school_course", "uw-cs-564")
            session.commit()
            student_courses.mark_taken(session, self.user_id, "uw-cs-564", "plan", UW)
        self.assertEqual([("uw-cs-564", "plan")], self.taken())

    def test_plan_hook_logs_instead_of_failing(self) -> None:
        with self.Session() as session, self.assertLogs(student_courses.logger, "WARNING"):
            student_courses.record_done_course(session, self.user_id, "uw-cs-000", UW)
            # The session is usable afterwards.
            student_courses.record_done_course(session, self.user_id, "uw-cs-564", UW)
        self.assertEqual([("uw-cs-564", "plan")], self.taken())

    def test_database_rules(self) -> None:
        with self.Session() as session:
            student_courses.mark_taken(session, self.user_id, "uw-cs-564", "manual", UW)
        with self.engine.connect() as connection:
            with self.assertRaises(IntegrityError):  # courses are never deleted while someone took them
                connection.execute(text("DELETE FROM school_courses WHERE id = 'uw-cs-564'"))
            connection.rollback()
            with self.assertRaises(IntegrityError):
                connection.execute(text("UPDATE student_courses SET source = 'other'"))
            connection.rollback()
        with self.engine.begin() as connection:  # deleting the account deletes its rows
            connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": self.user_id})
        self.assertEqual([], self.taken())


if __name__ == "__main__":
    unittest.main()
