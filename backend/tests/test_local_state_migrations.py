"""plan_items and Skill Gap storage migrations, rendered as offline SQL (no database)."""
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

PLAN_ITEMS = "3f8a1c6d2e90"
SKILL_GAP_RUNS = "6d7e2b9a4c15"
SKILL_GAP_RESULTS = "df5726089a8e"


class LocalStateMigrationTests(unittest.TestCase):
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

    def test_chain_follows_the_destinations_migration(self) -> None:
        self.assertEqual("1a7c4e9b2d60", self.script.get_revision(PLAN_ITEMS).down_revision)
        self.assertEqual(PLAN_ITEMS, self.script.get_revision(SKILL_GAP_RUNS).down_revision)

    def test_plan_items_one_row_per_user_role_and_resource(self) -> None:
        sql = self.render(PLAN_ITEMS, "upgrade")
        self.assertIn("CREATE TABLE plan_items", sql)
        self.assertIn("PRIMARY KEY (user_id, job_family, resource_id)", sql)
        self.assertIn("REFERENCES users (id) ON DELETE CASCADE", sql)
        self.assertIn("(status = 'done') = (done_at IS NOT NULL)", sql)
        self.assertIn("ALTER TABLE plan_items ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("DROP TABLE plan_items", self.render(PLAN_ITEMS, "downgrade"))

    def test_skill_gap_runs_belong_to_the_users_own_resume(self) -> None:
        sql = self.render(SKILL_GAP_RUNS, "upgrade")
        self.assertIn("CREATE TABLE skill_gap_runs", sql)
        self.assertIn("FOREIGN KEY(resume_id, user_id) REFERENCES resumes (id, user_id) ON DELETE CASCADE", sql)
        self.assertIn("ALTER TABLE skill_gap_runs ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("DROP TABLE skill_gap_runs", self.render(SKILL_GAP_RUNS, "downgrade"))

    def test_skill_gap_runs_allow_one_active_run_and_require_a_report_when_completed(self) -> None:
        sql = self.render(SKILL_GAP_RUNS, "upgrade")
        self.assertIn("CREATE UNIQUE INDEX uq_skill_gap_runs_one_active", sql)
        self.assertIn("WHERE status IN ('queued', 'running')", sql)
        self.assertIn("ck_skill_gap_runs_completed_report", sql)

    def test_skill_gap_results_follow_the_catalog_migration(self) -> None:
        self.assertEqual("c9413046949c", self.script.get_revision(SKILL_GAP_RESULTS).down_revision)

    def test_skill_gap_runs_gain_the_v3_storage_columns(self) -> None:
        sql = self.render(SKILL_GAP_RESULTS, "upgrade")
        for column in ("storage_schema_version", "resume_filename", "extraction_strategy", "partition_policy_version",
                       "selection_policy_version", "reuse_from_run_id", "match_score", "scored_skill_count",
                       "unscored_skill_count", "extraction_audit", "timings"):
            with self.subTest(column=column):
                self.assertIn(f"ALTER TABLE skill_gap_runs ADD COLUMN {column}", sql)
        self.assertIn("ck_skill_gap_runs_match_when_completed", sql)
        self.assertIn("ck_skill_gap_runs_v3_completed", sql)
        self.assertIn("UNIQUE (id, user_id, job_family)", sql)

    def test_one_branch_row_per_group_with_its_raw_answer(self) -> None:
        sql = self.render(SKILL_GAP_RESULTS, "upgrade")
        self.assertIn("CREATE TABLE skill_gap_run_branches", sql)
        self.assertIn("PRIMARY KEY (run_id, branch)", sql)
        self.assertIn("branch IN ('foundation', 'lifecycle', 'systems')", sql)
        self.assertIn("model_calls >= 0 AND model_calls <= 1", sql)
        self.assertIn("raw_output JSONB", sql)
        self.assertIn("REFERENCES skill_gap_runs (id) ON DELETE CASCADE", sql)
        self.assertIn("ALTER TABLE skill_gap_run_branches ENABLE ROW LEVEL SECURITY", sql)

    def test_one_result_row_per_skill_owned_by_its_run(self) -> None:
        sql = self.render(SKILL_GAP_RESULTS, "upgrade")
        self.assertIn("CREATE TABLE skill_gap_results", sql)
        self.assertIn("PRIMARY KEY (run_id, skill_id)", sql)
        self.assertIn("FOREIGN KEY(run_id, user_id, job_family) REFERENCES skill_gap_runs (id, user_id, job_family) "
                      "ON DELETE CASCADE", sql)
        self.assertIn("ck_skill_gap_results_scored_values", sql)
        self.assertIn("jsonb_typeof(evidence) = 'array'", sql)
        self.assertIn("UNIQUE (run_id, priority_rank)", sql)
        self.assertIn("ALTER TABLE skill_gap_results ENABLE ROW LEVEL SECURITY", sql)

    def test_skill_gap_results_downgrade_restores_the_original_runs_table(self) -> None:
        sql = self.render(SKILL_GAP_RESULTS, "downgrade")
        self.assertIn("DROP TABLE skill_gap_results", sql)
        self.assertIn("DROP TABLE skill_gap_run_branches", sql)
        self.assertIn("ALTER TABLE skill_gap_runs DROP COLUMN storage_schema_version", sql)
        self.assertIn("ALTER TABLE skill_gap_runs DROP CONSTRAINT uq_skill_gap_runs_id_user_family", sql)


if __name__ == "__main__":
    unittest.main()
