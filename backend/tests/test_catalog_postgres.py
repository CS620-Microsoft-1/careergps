"""Catalog tables, seed script and API responses against a real, throwaway Postgres with the real migrations.

Skipped unless CGPS_TEST_DATABASE_URL is set, so CI (no database) skips it. Never point it at the
shared Supabase database: it drops and recreates the public and auth schemas. For example:

    CGPS_TEST_DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5433/scratch_db \
        python -m unittest tests.test_catalog_postgres
"""
import os
import subprocess
import sys
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import BACKEND_ROOT
from app.models.catalog import CatalogVersion
from app.schemas.certifications import CertificationCatalog
from app.schemas.resources import ResourceList
from app.services import catalog_store, catalog_writes
from app.services.catalog_store import DatabaseCatalogSource, FileCatalogSource
from app.services.certifications.catalog import for_family, get_catalog
from app.services.resources import load_catalog, resources_for
from scripts.seed_catalog import seed

DATABASE_URL = os.environ.get("CGPS_TEST_DATABASE_URL")
FAMILIES = ("software_engineer", "data_analyst", "ai_engineer")
# resources.yaml plus the course guide data (data/uw_courses).
COURSES = sum(entry["type"] == "school_course" for entry in load_catalog())
SCHOOLS = ("University of Wisconsin–Madison", "UW-Madison", "Another University", None)


def _responses() -> dict:
    """/resources and /certifications/catalog bodies, through the same response models as the routes."""
    bodies = {}
    for family in FAMILIES:
        for school in SCHOOLS:
            bodies[f"resources/{family}/{school}"] = ResourceList(
                job_family=family, resources=resources_for(family, school)).model_dump(mode="json")
        catalog = get_catalog()
        bodies[f"certifications/{family}"] = CertificationCatalog(
            job_family=family, version=catalog["version"], certifications=for_family(catalog, family),
        ).model_dump(mode="json")
    return bodies


@unittest.skipUnless(DATABASE_URL, "set CGPS_TEST_DATABASE_URL to a throwaway local Postgres to run")
class CatalogPostgresTests(unittest.TestCase):
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
            # A schema without the catalog tables, as before the migration is applied.
            connection.execute(text("DROP SCHEMA IF EXISTS catalog_missing CASCADE; CREATE SCHEMA catalog_missing"))
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, check=True,
                       capture_output=True,
                       env={**os.environ, "DATABASE_URL": DATABASE_URL, "MIGRATION_DATABASE_URL": DATABASE_URL})
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        catalog_store.use_source(FileCatalogSource())
        cls.expected = _responses()  # read from the files: the responses before the move

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS catalog_missing CASCADE"))
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE student_courses, certifications, school_courses, student_orgs, catalog_versions"))
        catalog_store.use_source(DatabaseCatalogSource(self.Session))

    def tearDown(self) -> None:
        catalog_store.use_source(FileCatalogSource())

    def seed(self, **options) -> dict:
        with self.Session() as session:
            counts = seed(session, **options)
            session.commit()
        return {table: dict(counter) for table, counter in counts.items()}

    def row(self, kind: str, row_id: str):
        with self.Session() as session:
            return catalog_writes.get_row(session, kind, row_id)

    def version(self) -> str:
        with self.Session() as session:
            return session.get(CatalogVersion, catalog_writes.CERTIFICATIONS).version

    def test_seeded_database_gives_the_same_responses_as_the_files(self) -> None:
        self.assertEqual({"certifications": {"inserted": 48}, "school_courses": {"inserted": COURSES},
                          "student_orgs": {"inserted": 2}}, self.seed())
        self.assertEqual("database", catalog_store.get_snapshot().source)
        self.assertEqual("2026-10-26", self.version())
        actual = _responses()
        for key, body in self.expected.items():
            self.assertEqual(body, actual[key], key)

    def test_seed_again_changes_nothing(self) -> None:
        self.seed()
        self.assertEqual({"certifications": {"skipped": 48}, "school_courses": {"skipped": COURSES},
                          "student_orgs": {"skipped": 2}}, self.seed())
        self.assertEqual({"certifications": {"unchanged": 48}, "school_courses": {"unchanged": COURSES},
                          "student_orgs": {"unchanged": 2}}, self.seed(update=True))
        self.assertEqual("2026-10-26", self.version())

    def test_seed_keeps_other_writers_changes_unless_told_to_update(self) -> None:
        self.seed()
        with self.Session() as session:
            row = catalog_writes.get_row(session, "certification", "aws-cloud-practitioner")
            data = {"id": row.id, "name": row.name, "provider": row.provider, "url": row.url,
                    "cost_usd": 150, "cost_note": row.cost_note, "level": row.level, "skills": row.skills}
            catalog_writes.upsert_certification(session, data, verified_at=date(2026, 11, 8))
            session.commit()
        self.seed()
        self.assertEqual(150, self.row("certification", "aws-cloud-practitioner").cost_usd)
        self.assertEqual({"updated": 1, "unchanged": 47}, self.seed(update=True)["certifications"])
        self.assertEqual(100, self.row("certification", "aws-cloud-practitioner").cost_usd)

    def test_missing_or_empty_tables_fall_back_to_the_files(self) -> None:
        with self.assertLogs(catalog_store.logger, "WARNING"):
            self.assertEqual("files", catalog_store.get_snapshot().source)  # empty tables
        missing = create_engine(DATABASE_URL, connect_args={"options": "-c search_path=catalog_missing"})
        try:
            catalog_store.use_source(DatabaseCatalogSource(sessionmaker(bind=missing)))
            with self.assertLogs(catalog_store.logger, "WARNING") as logs:
                self.assertEqual("files", catalog_store.get_snapshot().source)
            self.assertIn("missing", logs.output[0])
        finally:
            missing.dispose()

    def test_version_changes_once_per_transaction_and_only_for_recommendation_fields(self) -> None:
        self.seed()
        catalog_store.get_snapshot()
        with self.Session() as session:
            row = catalog_writes.get_row(session, "certification", "aws-cloud-practitioner")
            data = {"id": row.id, "name": row.name, "provider": row.provider, "url": row.url,
                    "cost_usd": row.cost_usd, "cost_note": row.cost_note, "level": row.level, "skills": row.skills}
            # Checked again: new date and page, same content. Recommendations stay cached.
            self.assertEqual("updated", catalog_writes.upsert_certification(
                session, data, verified_at=date(2026, 11, 8), source_url="https://example.com/checked"))
            self.assertEqual("unchanged", catalog_writes.upsert_certification(
                session, data, verified_at=date(2026, 11, 8)))
            session.commit()
        self.assertEqual("2026-10-26", self.version())

        versions = iter(["v-first", "v-second"])
        with patch.object(catalog_writes, "_new_version", lambda: next(versions)), self.Session() as session:
            catalog_writes.upsert_certification(session, {**data, "cost_usd": 120}, verified_at=date(2026, 11, 8))
            catalog_writes.deactivate(session, "certification", "aws-solutions-architect-associate")
            # Not listed until the commit, then listed without waiting for the cache to expire.
            self.assertEqual("2026-10-26", catalog_store.get_snapshot().certification_version)
            session.commit()
        self.assertEqual("v-first", self.version())
        self.assertEqual("v-first", get_catalog()["version"])
        ids = {item.id for item in get_catalog()["certifications"]}
        self.assertNotIn("aws-solutions-architect-associate", ids)
        self.assertEqual(47, len(ids))

    def test_deactivated_rows_stay_readable_and_can_come_back(self) -> None:
        self.seed()
        with self.Session() as session:
            self.assertTrue(catalog_writes.deactivate(session, "school_course", "uw-cs-564"))
            self.assertFalse(catalog_writes.deactivate(session, "school_course", "uw-cs-564"))
            session.commit()
        listed = {entry["id"] for entry in resources_for("data_analyst", "UW-Madison")}
        self.assertNotIn("uw-cs-564", listed)
        with self.Session() as session:
            self.assertFalse(catalog_writes.get_row(session, "school_course", "uw-cs-564").active)
            self.assertTrue(catalog_writes.reactivate(session, "school_course", "uw-cs-564"))
            with self.assertRaises(KeyError):
                catalog_writes.reactivate(session, "student_org", "no-such-org")
            session.commit()
        self.assertIn("uw-cs-564", {entry["id"] for entry in resources_for("data_analyst", "UW-Madison")})
        self.assertEqual("2026-10-26", self.version())  # courses don't change the certification version

    def test_new_rows_go_last(self) -> None:
        self.seed()
        with self.Session() as session:
            catalog_writes.upsert_student_org(session, {
                "id": "uw-new-club", "title": "New club", "provider": "UW–Madison student org", "meta": "Weekly",
                "description": "Meets weekly.", "skills": ["python"], "school": "University of Wisconsin–Madison",
                "alongside": True, "url": "https://example.com/club"}, verified_at=date(2026, 11, 8))
            session.commit()
        orgs = catalog_store.get_snapshot().student_orgs
        self.assertEqual("uw-new-club", orgs[-1]["id"])
        self.assertEqual(3, len(orgs))

    def test_a_rolled_back_write_changes_nothing(self) -> None:
        self.seed()
        with self.Session() as session:
            catalog_writes.deactivate(session, "certification", "aws-cloud-practitioner")
            session.rollback()
        self.assertTrue(self.row("certification", "aws-cloud-practitioner").active)
        self.assertEqual("2026-10-26", self.version())


if __name__ == "__main__":
    unittest.main()
