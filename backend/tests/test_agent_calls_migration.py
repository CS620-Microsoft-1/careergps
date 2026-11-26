"""The agent_calls migration, rendered as offline SQL (no database)."""
import io
import unittest
from unittest.mock import patch

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT

REVISION = "9ea89c504d80"


class AgentCallsMigrationTests(unittest.TestCase):
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

    def test_follows_student_courses(self) -> None:
        self.assertEqual("9aa1698efdd2", self.script.get_revision(REVISION).down_revision)

    def test_creates_agent_calls_with_checks_indexes_cascade_and_rls(self) -> None:
        sql = self.render("upgrade")
        self.assertIn("CREATE TABLE agent_calls (", sql)
        self.assertIn("cost_usd NUMERIC(14, 8)", sql)
        self.assertIn("CONSTRAINT ck_agent_calls_status CHECK", sql)
        self.assertIn("CREATE INDEX ix_agent_calls_agent_created_at ON agent_calls (agent, created_at)", sql)
        self.assertIn("ALTER TABLE agent_calls ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE agent_calls ADD CONSTRAINT fk_agent_calls_user FOREIGN KEY (user_id) "
                      "REFERENCES auth.users (id) ON DELETE CASCADE", sql)
        self.assertEqual(1, sql.count("FOREIGN KEY"))
        self.assertNotIn("INSERT", sql)
        self.assertIn("DROP TABLE agent_calls", self.render("downgrade"))


if __name__ == "__main__":
    unittest.main()
