"""The destinations migrations, rendered as offline SQL (no database)."""
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

from app.models import Destination, Resume, User  # noqa: E402

REVISION = "1a7c4e9b2d60"
PARENT_REVISION = "7d2c91a4e8b6"
DROP_REVISION = "9c4d2a7f1b3e"


class DestinationsMigrationTests(unittest.TestCase):
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

    def test_follows_the_job_analysis_migration(self) -> None:
        self.assertEqual(PARENT_REVISION, self.script.get_revision(REVISION).down_revision)

    def test_one_row_per_user_and_role_pointing_at_the_users_own_resume(self) -> None:
        sql = self.render(REVISION, "upgrade")
        self.assertIn("CREATE TABLE destinations", sql)
        self.assertIn("PRIMARY KEY (user_id, job_family)", sql)
        self.assertIn("FOREIGN KEY(resume_id, user_id) REFERENCES resumes (id, user_id)", sql)
        self.assertIn("ALTER TABLE destinations ENABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("DROP COLUMN", sql)

    def test_backfills_the_target_role_with_the_active_resume(self) -> None:
        sql = self.render(REVISION, "upgrade")
        self.assertIn("INSERT INTO destinations (user_id, job_family, resume_id)", sql)
        self.assertIn("u.active_resume_id IS NOT NULL", sql)
        self.assertIn("DROP TABLE destinations", self.render(REVISION, "downgrade"))

    def test_drop_is_the_single_head_and_syncs_the_pointer_first(self) -> None:
        self.assertEqual([DROP_REVISION], self.script.get_heads())
        sql = self.render(DROP_REVISION, "upgrade")
        # Never overwrite a destination: the code that ships with this migration no longer
        # updates active_resume_id, so an existing destination can be newer than the pointer.
        self.assertIn("ON CONFLICT (user_id, job_family) DO NOTHING", sql)
        self.assertNotIn("DO UPDATE", sql)
        self.assertLess(sql.index("INSERT INTO destinations"), sql.index("DROP COLUMN active_resume_id"))
        self.assertIn("ADD COLUMN active_resume_id UUID", self.render(DROP_REVISION, "downgrade"))

    def test_models_match(self) -> None:
        self.assertEqual({"user_id", "job_family", "resume_id", "created_at", "updated_at"},
                         set(Destination.__table__.columns.keys()))
        self.assertNotIn("job_family", Resume.__table__.columns)
        self.assertNotIn("active_resume_id", User.__table__.columns)


if __name__ == "__main__":
    unittest.main()
