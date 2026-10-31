"""migrations/env.py's autogenerate filter, loaded through Alembic offline (no database)."""
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


class IncludeObjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # No alembic.ini: env.py then skips fileConfig, which would reset logging for other tests.
        config = Config(output_buffer=io.StringIO())
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        script = ScriptDirectory.from_config(config)
        with EnvironmentContext(config, script, fn=lambda rev, context: [], as_sql=True) as env:
            script.run_env()
            cls.include_object = staticmethod(env.get_context().opts["include_object"])

    def test_never_drops_a_table_that_has_no_model(self) -> None:
        for name in ("plan_items", "skill_gap_runs"):
            self.assertFalse(self.include_object(SimpleNamespace(name=name), name, "table", True, None))

    def test_still_compares_tables_that_have_models(self) -> None:
        self.assertTrue(self.include_object(object(), "users", "table", True, object()))
        self.assertTrue(self.include_object(object(), "new_table", "table", False, None))
        self.assertTrue(self.include_object(object(), "ix", "index", True, None))

    def test_ignores_foreign_keys_into_auth(self) -> None:
        auth_fk = SimpleNamespace(referred_table=SimpleNamespace(schema="auth"))
        public_fk = SimpleNamespace(referred_table=SimpleNamespace(schema=None))
        self.assertFalse(self.include_object(auth_fk, "fk", "foreign_key_constraint", True, None))
        self.assertTrue(self.include_object(public_fk, "fk", "foreign_key_constraint", True, None))


if __name__ == "__main__":
    unittest.main()
