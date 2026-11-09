"""The catalog tables migration, rendered as offline SQL (no database)."""
import io
import unittest
from unittest.mock import patch

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT

REVISION = "c9413046949c"
TABLES = ("certifications", "school_courses", "student_orgs", "catalog_versions")


class CatalogMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))

    def render(self, direction: str) -> str:
        module = self.script.get_revision(REVISION).module
        output = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output, "literal_binds": True}
        )
        with patch("sqlalchemy.create_engine", side_effect=AssertionError("No database access")), \
             patch.object(module, "op", Operations(context)):
            getattr(module, direction)()
        return output.getvalue()

    def test_follows_the_drop_active_resume_migration(self) -> None:
        self.assertEqual("9c4d2a7f1b3e", self.script.get_revision(REVISION).down_revision)

    def test_creates_the_tables_with_rls_and_no_data(self) -> None:
        sql = self.render("upgrade")
        for table in TABLES:
            self.assertIn(f"CREATE TABLE {table} (", sql)
            self.assertIn(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("INSERT", sql)
        self.assertIn("alongside BOOLEAN DEFAULT false NOT NULL", sql)
        self.assertIn("skills JSONB NOT NULL", sql)

    def test_downgrade_drops_the_tables(self) -> None:
        sql = self.render("downgrade")
        for table in TABLES:
            self.assertIn(f"DROP TABLE {table}", sql)


if __name__ == "__main__":
    unittest.main()
