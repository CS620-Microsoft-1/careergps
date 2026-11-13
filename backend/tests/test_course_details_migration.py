"""The school course details migration, rendered as offline SQL (no database)."""
import io
import unittest
from unittest.mock import patch

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT

REVISION = "e93b20128bb7"


class CourseDetailsMigrationTests(unittest.TestCase):
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

    def test_follows_the_skill_gap_storage_migration(self) -> None:
        self.assertEqual("df5726089a8e", self.script.get_revision(REVISION).down_revision)

    def test_adds_nullable_course_details_and_no_prerequisites(self) -> None:
        sql = self.render(REVISION, "upgrade")
        for column in ("course_code", "credits", "last_taught"):
            self.assertIn(f"ALTER TABLE school_courses ADD COLUMN {column} TEXT;", sql)
        self.assertNotIn("requisite", sql.lower())
        self.assertIn("DROP COLUMN course_code", self.render(REVISION, "downgrade"))


if __name__ == "__main__":
    unittest.main()
