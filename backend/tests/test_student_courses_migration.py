"""The student_courses migration, rendered as offline SQL (no database)."""
import io
import unittest
from unittest.mock import patch

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT

REVISION = "9aa1698efdd2"


class StudentCoursesMigrationTests(unittest.TestCase):
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

    def test_follows_the_course_details_migration(self) -> None:
        self.assertEqual("e93b20128bb7", self.script.get_revision(REVISION).down_revision)

    def test_creates_student_courses_with_foreign_keys_and_rls(self) -> None:
        sql = self.render(REVISION, "upgrade")
        self.assertIn("CREATE TABLE student_courses (", sql)
        self.assertIn("FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE", sql)
        self.assertIn("FOREIGN KEY(course_id) REFERENCES school_courses (id) ON DELETE RESTRICT", sql)
        self.assertIn("PRIMARY KEY (user_id, course_id)", sql)
        self.assertIn("ALTER TABLE student_courses ENABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("INSERT", sql)
        self.assertIn("DROP TABLE student_courses", self.render(REVISION, "downgrade"))


if __name__ == "__main__":
    unittest.main()
