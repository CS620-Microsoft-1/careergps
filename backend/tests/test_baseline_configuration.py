import importlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:placeholder@localhost:6543/test")

from app.core.config import Settings, get_settings
from app.db.base import Base
import app.db.session
import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.models.user import User


def migration_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (BACKEND_ROOT / "migrations" / "versions").glob("*.py")
    )


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class RepositorySafetyTests(unittest.TestCase):
    def test_local_environment_paths_are_ignored(self) -> None:
        paths = (
            "backend/.env",
            "backend/.venv/pyvenv.cfg",
            "backend/.venv-jd-test/pyvenv.cfg",
            "backend/local_tests/scratch.py",
            "backend/local_exports/api_tests/output.txt",
        )
        result = run_git("check-ignore", *paths)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(paths), set(result.stdout.splitlines()))

    def test_sensitive_environment_files_are_not_tracked(self) -> None:
        result = run_git("ls-files")
        self.assertEqual(result.returncode, 0, result.stderr)

        unsafe_paths = []
        for raw_path in result.stdout.splitlines():
            path = Path(raw_path)
            if any(part.startswith(".venv") for part in path.parts) or raw_path.startswith(
                ("backend/local_tests/", "backend/local_exports/")
            ):
                unsafe_paths.append(raw_path)
            if path.name == ".env" or (
                path.name.startswith(".env.") and path.name != ".env.example"
            ):
                unsafe_paths.append(raw_path)

        self.assertEqual([], unsafe_paths, f"Tracked sensitive paths: {unsafe_paths}")

    def test_environment_example_contains_placeholders_only(self) -> None:
        example = (BACKEND_ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("DATABASE_URL=", example)
        self.assertIn("<project-ref>", example)
        self.assertIn("<db-password>", example)
        self.assertIn("<region>", example)

    def test_environment_example_uses_transaction_pooler_for_the_app(self) -> None:
        example = (BACKEND_ROOT / ".env.example").read_text(encoding="utf-8")
        app_url = next(line for line in example.splitlines() if line.startswith("DATABASE_URL="))

        self.assertIn(".pooler.supabase.com:6543/", app_url)
        self.assertIn("MIGRATION_DATABASE_URL=", example)
        self.assertIn(".pooler.supabase.com:5432/", example.split("MIGRATION_DATABASE_URL=", 1)[1])


class BackendConfigurationTests(unittest.TestCase):
    def test_engine_disables_prepared_statements_for_the_transaction_pooler(self) -> None:
        env = {"DATABASE_URL": "postgresql+psycopg://tester:placeholder@localhost:6543/test"}
        with patch.dict(os.environ, env), patch("sqlalchemy.create_engine") as create_engine:
            get_settings.cache_clear()
            try:
                importlib.reload(app.db.session)
            finally:
                get_settings.cache_clear()
        importlib.reload(app.db.session)

        self.assertEqual({"prepare_threshold": None}, create_engine.call_args.kwargs["connect_args"])

    def test_migration_url_is_optional(self) -> None:
        settings = Settings(_env_file=None, database_url="postgresql+psycopg://x:y@localhost:6543/z")

        self.assertIsNone(settings.migration_database_url)

    def test_required_dependencies_are_declared(self) -> None:
        requirements = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")

        for dependency in (
            "sqlalchemy",
            "psycopg",
            "alembic",
            "python-dotenv",
            "fastapi",
            "uvicorn",
            "pydantic-settings",
        ):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, requirements.lower())

    def test_alembic_has_exactly_one_head(self) -> None:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)

        self.assertEqual(1, len(script.get_heads()), script.get_heads())

    def test_job_analysis_tables_are_registered_for_future_persistence(self) -> None:
        for table in (
            "job_postings_analyses", "job_analysis_locations",
            "job_analysis_responsibilities", "job_analysis_qualifications",
            "job_analysis_conditions", "job_analysis_compensation",
        ):
            with self.subTest(table=table):
                self.assertIn(table, Base.metadata.tables)
                self.assertIn("job_posting_id", Base.metadata.tables[table].columns)

    def test_user_model_has_expected_table_and_columns(self) -> None:
        self.assertEqual("users", User.__tablename__)
        self.assertEqual(
            {
                "id",
                "primary_email",
                "first_name",
                "last_name",
                "full_name",
                "target_role",
                "experience_level",
                "graduation_year",
                "university",
                "preferred_location",
                "resume_emails",
                "phones",
                "current_location",
                "linkedin_url",
                "github_url",
                "website_url",
                "terms_accepted_at",
                "created_at",
                "updated_at",
            },
            set(User.__table__.columns.keys()),
        )
        self.assertTrue(User.__table__.columns.primary_email.unique)
        self.assertFalse(User.__table__.columns.primary_email.nullable)
        # The id comes from Supabase Auth, never from Python.
        self.assertIsNone(User.__table__.columns.id.default)

    def test_resume_tables_are_registered_with_their_owner_columns(self) -> None:
        self.assertIn("confirmed_data", Base.metadata.tables["resumes"].columns)
        for table in (
            "resume_experiences",
            "resume_educations",
            "resume_projects",
            "resume_achievements",
            "resume_skills",
        ):
            with self.subTest(table=table):
                columns = Base.metadata.tables[table].columns
                self.assertTrue({"id", "resume_id", "user_id", "created_at"} <= set(columns.keys()))

    def test_users_migration_enables_rls(self) -> None:
        self.assertIn("ALTER TABLE users ENABLE ROW LEVEL SECURITY", migration_text())

    def test_users_reference_supabase_auth_accounts(self) -> None:
        # Written by hand in a migration; autogenerate can't create or see it.
        self.assertIn("REFERENCES auth.users (id) ON DELETE CASCADE", migration_text())

    def test_job_posting_migration_enables_rls(self) -> None:
        for table in ("job_postings", "ingest_runs"):
            with self.subTest(table=table):
                self.assertIn(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", migration_text())

    def test_resume_migration_enables_rls(self) -> None:
        for table in (
            "resumes",
            "resume_experiences",
            "resume_educations",
            "resume_projects",
            "resume_achievements",
            "resume_skills",
        ):
            with self.subTest(table=table):
                self.assertIn(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", migration_text())


if __name__ == "__main__":
    unittest.main()
