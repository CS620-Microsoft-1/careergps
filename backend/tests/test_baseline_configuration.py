import subprocess
import sys
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.user import User


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
        result = run_git(
            "check-ignore",
            "backend/.env",
            "backend/.venv/pyvenv.cfg",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        ignored = set(result.stdout.splitlines())
        self.assertIn("backend/.env", ignored)
        self.assertIn("backend/.venv/pyvenv.cfg", ignored)

    def test_sensitive_environment_files_are_not_tracked(self) -> None:
        result = run_git("ls-files")
        self.assertEqual(result.returncode, 0, result.stderr)

        unsafe_paths = []
        for raw_path in result.stdout.splitlines():
            path = Path(raw_path)
            if ".venv" in path.parts:
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


class BackendConfigurationTests(unittest.TestCase):
    def test_required_dependencies_are_declared(self) -> None:
        requirements = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")

        for dependency in ("sqlalchemy", "psycopg", "alembic", "python-dotenv"):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, requirements.lower())

    def test_alembic_has_exactly_one_head(self) -> None:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)

        self.assertEqual(1, len(script.get_heads()), script.get_heads())

    def test_user_model_has_expected_table_and_columns(self) -> None:
        self.assertEqual("users", User.__tablename__)
        self.assertEqual(
            {"id", "email", "full_name", "created_at", "updated_at"},
            set(User.__table__.columns.keys()),
        )
        self.assertTrue(User.__table__.columns.email.unique)
        self.assertFalse(User.__table__.columns.email.nullable)

    def test_users_migration_enables_rls(self) -> None:
        migration_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (BACKEND_ROOT / "migrations" / "versions").glob("*.py")
        )

        self.assertIn("ALTER TABLE users ENABLE ROW LEVEL SECURITY", migration_text)


if __name__ == "__main__":
    unittest.main()
