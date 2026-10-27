"""The résumé-per-destination migration, rendered as offline SQL (no database)."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

REVISION = "5b1e9c3f7a2d"
PARENT_REVISION = "7d2c91a4e8b6"


class ResumeDestinationMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))

    def render(self, revision: str, direction: str) -> str:
        module = self.script.get_revision(revision).module
        output = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output, "literal_binds": True}
        )
        with patch("sqlalchemy.create_engine", side_effect=AssertionError("No database access")), \
             patch.object(module, "op", Operations(context)):
            getattr(module, direction)()
        return output.getvalue()

    def test_link_is_the_single_head_after_the_job_analysis_migration(self) -> None:
        self.assertEqual([REVISION], self.script.get_heads())
        self.assertEqual(PARENT_REVISION, self.script.get_revision(REVISION).down_revision)

    def test_link_adds_the_column_and_backfills_without_touching_the_pointer(self) -> None:
        sql = self.render(REVISION, "upgrade")
        self.assertIn("ALTER TABLE resumes ADD COLUMN job_family TEXT", sql)
        self.assertIn("ck_resumes_job_family", sql)
        self.assertIn("WHERE u.active_resume_id = r.id", sql)
        self.assertNotIn("DROP COLUMN", sql)
        self.assertIn("DROP COLUMN job_family", self.render(REVISION, "downgrade"))


if __name__ == "__main__":
    unittest.main()
