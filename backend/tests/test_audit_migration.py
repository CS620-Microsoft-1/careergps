"""The audit_log migration, rendered as offline SQL (no database)."""
import io
import unittest
from unittest.mock import patch

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT

REVISION = "3cbf0057f8a3"


class AuditLogMigrationTests(unittest.TestCase):
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

    def test_follows_agent_calls_and_is_the_only_head(self) -> None:
        self.assertEqual("9ea89c504d80", self.script.get_revision(REVISION).down_revision)
        self.assertEqual([REVISION], self.script.get_heads())

    def test_creates_audit_log_with_cascade_rls_and_the_view(self) -> None:
        sql = self.render("upgrade")
        self.assertIn("CREATE TABLE audit_log (", sql)
        self.assertIn("CONSTRAINT ck_audit_log_source CHECK (source IN ('api', 'script'))", sql)
        self.assertIn("ALTER TABLE audit_log ADD CONSTRAINT fk_audit_log_user FOREIGN KEY (user_id) "
                      "REFERENCES auth.users (id) ON DELETE CASCADE", sql)
        self.assertIn("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("CREATE VIEW audit_events WITH (security_invoker = true) AS", sql)
        self.assertIn("FROM agent_calls", sql)
        self.assertNotIn("INSERT", sql)
        downgrade = self.render("downgrade")
        self.assertLess(downgrade.index("DROP VIEW audit_events"), downgrade.index("DROP TABLE audit_log"))


if __name__ == "__main__":
    unittest.main()
