"""Offline JPA contract/DDL tests; never connect to PostgreSQL, Supabase or Azure.

Compile the migration with the PostgreSQL dialect, compare it with ORM metadata,
and verify the selected relational projection of the unchanged live output contract.
PostgreSQL CHECK enforcement and live RLS behavior require a separate local DB test.
"""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Numeric, Text, UniqueConstraint, select
from sqlalchemy.dialects import postgresql

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import Base
from app.models.job_posting import JobPosting
from app.models.job_posting_analysis import (
    COMPENSATION_TYPES,
    CONDITION_TYPES,
    JOB_FAMILIES,
    PAY_INTERVALS,
    QUALIFICATION_CATEGORIES,
    QUALIFICATION_LEVELS,
    SENIORITIES,
    JobAnalysisCompensation,
    JobAnalysisCondition,
    JobAnalysisLocation,
    JobAnalysisQualification,
    JobAnalysisResponsibility,
    JobPostingAnalysis,
)
from app.schemas.job_posting_analysis import _validator, validate_analysis_response
from app.services.job_posting_analysis_agent import validate_analysis_content
from tests.test_job_posting_analysis_agent import JOB_ID, analysis_fixture, posting_fixture


CHILDREN = {
    "locations": JobAnalysisLocation,
    "responsibilities": JobAnalysisResponsibility,
    "qualifications": JobAnalysisQualification,
    "job_conditions": JobAnalysisCondition,
    "compensation": JobAnalysisCompensation,
}
TABLES = {m.__tablename__: m.__table__ for m in (JobPostingAnalysis, *CHILDREN.values())}
REVISION = "7d2c91a4e8b6"
PARENT_REVISION = "02a858fed0df"
DIALECT = postgresql.dialect()


def enum_values(definition: dict) -> tuple[str, ...]:
    if "enum" in definition:
        return tuple(definition["enum"])
    return next(tuple(branch["enum"]) for branch in definition["anyOf"] if "enum" in branch)


def table_signature(table) -> dict:
    """Compare persisted DDL semantics; Python-only defaults/onupdate are excluded."""
    def default(column):
        return str(column.server_default.arg.compile(dialect=DIALECT)) if column.server_default else None

    return {
        "columns": {
            c.name: (str(c.type.compile(dialect=DIALECT)), c.nullable, c.primary_key, default(c))
            for c in table.columns
        },
        "checks": {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        },
        "unique": {
            c.name: tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)
        },
        "foreign_keys": {
            (tuple(c.columns.keys()), tuple(e.target_fullname for e in c.elements), c.ondelete)
            for c in table.constraints if isinstance(c, ForeignKeyConstraint)
        },
    }


class JobAnalysisModelTests(unittest.TestCase):
    def test_unchanged_contract_has_an_explicit_storage_projection(self) -> None:
        schema = _validator().schema
        main = JobPostingAnalysis.__table__
        retained = {
            "id": "job_posting_id", "content_hash": "source_content_hash",
            "job_family": "job_family", "seniority": "seniority",
            "role_overview": "role_overview", "benefits": "benefits",
            "other_relevant_information": "other_relevant_information",
        }
        source_metadata = {
            "source", "external_id", "company_slug", "company_tier", "url",
            "published_at", "first_seen_at", "last_seen_at", "closed_at",
            "created_at", "updated_at",
        }
        # These five are not exact copies by contract. We deliberately prefer
        # source identity fields and per-arrangement compensation over storing
        # Agent enrichment/summary scalars. Only the local JSON keeps them all.
        omitted_agent_fields = {
            "company_name": "company_name", "job_title": "title",
            "department": "department", "salary_currency": "salary_currency",
            "salary_interval": "salary_interval",
        }
        self.assertEqual(28, len(schema["properties"]))
        self.assertEqual(
            set(schema["properties"]),
            set(retained) | source_metadata | set(omitted_agent_fields) | set(CHILDREN),
        )
        for column in retained.values():
            self.assertIn(column, main.columns)
        for field in source_metadata | set(omitted_agent_fields):
            self.assertNotIn(field, main.columns)
            self.assertIn(omitted_agent_fields.get(field, field), JobPosting.__table__.columns)
        self.assertIsInstance(main.c.role_overview.type, Text)
        self.assertIsInstance(main.c.role_overview_evidence.type, postgresql.JSONB)
        for field, model in CHILDREN.items():
            with self.subTest(field=field):
                item = schema["properties"][field]["items"]
                definition = schema["$defs"][item["$ref"].rsplit("/", 1)[-1]]
                self.assertEqual(set(definition["properties"]), set(model.__table__.columns.keys()) - {
                    "id", "job_posting_id", "position",
                })
        self.assertNotIn("structured_data", main.columns)
        self.assertNotIn("qualifications", main.columns)

    def test_database_enums_match_the_active_agent_contract(self) -> None:
        definitions = _validator().schema["$defs"]
        cases = (
            (JOB_FAMILIES, definitions["job_family"]),
            (SENIORITIES, definitions["seniority"]),
            (PAY_INTERVALS, definitions["base_pay_interval"]),
            (QUALIFICATION_LEVELS, definitions["qualification"]["properties"]["level"]),
            (QUALIFICATION_CATEGORIES, definitions["qualification"]["properties"]["categories"]["items"]),
            (CONDITION_TYPES, definitions["job_condition"]["properties"]["type"]),
            (COMPENSATION_TYPES, definitions["compensation_item"]["properties"]["type"]),
            (PAY_INTERVALS, definitions["compensation_item"]["properties"]["interval"]),
        )
        for expected, definition in cases:
            with self.subTest(values=expected):
                self.assertEqual(expected, enum_values(definition))

    def test_one_analysis_per_source_job_without_user_or_resume_ownership(self) -> None:
        parent = JobPostingAnalysis.__table__
        self.assertEqual(["job_posting_id"], list(parent.primary_key.columns.keys()))
        self.assertIsNone(parent.c.job_posting_id.default)
        self.assertIsNone(parent.c.job_posting_id.server_default)
        fk = next(iter(parent.c.job_posting_id.foreign_keys))
        self.assertEqual("job_postings.id", fk.target_fullname)
        self.assertEqual("CASCADE", fk.ondelete)
        for name, table in TABLES.items():
            with self.subTest(table=name):
                self.assertIs(Base.metadata.tables[name], table)
                self.assertNotIn("user_id", table.columns)
                self.assertNotIn("resume_id", table.columns)
                self.assertNotIn("status", table.columns)

    def test_details_have_independent_ids_and_ordered_per_job_lookup(self) -> None:
        for name, model in CHILDREN.items():
            with self.subTest(field=name):
                table = model.__table__
                self.assertEqual(["id"], list(table.primary_key.columns.keys()))
                self.assertIsNotNone(table.c.id.default)
                self.assertEqual("gen_random_uuid()", str(table.c.id.server_default.arg))
                fk = next(iter(table.c.job_posting_id.foreign_keys))
                self.assertEqual("job_postings_analyses.job_posting_id", fk.target_fullname)
                self.assertEqual("CASCADE", fk.ondelete)
                uniques = [tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)]
                self.assertEqual([("job_posting_id", "position")], uniques)
                self.assertIsInstance(table.c.value.type, Text)
                self.assertIsInstance(table.c.evidence.type, postgresql.JSONB)
                self.assertFalse(table.c.evidence.nullable)

    def test_unknown_scalars_and_partial_compensation_can_be_stored(self) -> None:
        for field in ("job_family", "seniority", "source_content_hash", "role_overview"):
            self.assertTrue(JobPostingAnalysis.__table__.c[field].nullable)
        for field in ("minimum", "maximum", "currency", "interval", "applies_to"):
            self.assertTrue(JobAnalysisCompensation.__table__.c[field].nullable)
        for field in ("minimum", "maximum"):
            amount = JobAnalysisCompensation.__table__.c[field]
            self.assertIsInstance(amount.type, Numeric)
            self.assertIsNone(amount.type.scale)  # Do not round Agent amounts to a fixed scale.
        self.assertIsInstance(JobPostingAnalysis.__table__.c.benefits.type, Text)
        self.assertIsInstance(JobPostingAnalysis.__table__.c.other_relevant_information.type, postgresql.ARRAY)

    def test_parent_has_exactly_ten_columns_including_analysis_provenance(self) -> None:
        main = JobPostingAnalysis.__table__
        expected = {
            "job_posting_id", "job_family", "seniority", "role_overview",
            "role_overview_evidence", "benefits", "other_relevant_information",
            "source_content_hash", "agent_version", "analyzed_at",
        }
        self.assertEqual(10, len(main.columns))
        self.assertEqual(expected, set(main.columns.keys()))
        self.assertTrue({
            "source_snapshot", "agent_name", "schema_version", "is_open",
            "created_at", "updated_at", "source_created_at", "source_updated_at",
        }.isdisjoint(main.columns.keys()))

    def test_provenance_is_required_without_insert_time_or_version_defaults(self) -> None:
        main = JobPostingAnalysis.__table__
        self.assertIsInstance(main.c.agent_version.type, Text)
        self.assertIsInstance(main.c.analyzed_at.type, DateTime)
        self.assertTrue(main.c.analyzed_at.type.timezone)
        for name in ("agent_version", "analyzed_at"):
            with self.subTest(field=name):
                column = main.c[name]
                self.assertFalse(column.nullable)
                self.assertIsNone(column.default)
                self.assertIsNone(column.server_default)
                self.assertIsNone(column.onupdate)

    def test_provenance_and_availability_do_not_change_agent_contract(self) -> None:
        from app.schemas.job_posting_analysis import JobPostingAnalysisValidationError

        for name, value in (("agent_version", "13"),
                            ("analyzed_at", "2026-10-22T12:00:00+00:00"),
                            ("is_open", True)):
            with self.subTest(field=name):
                self.assertNotIn(name, _validator().schema["properties"])
                payload = analysis_fixture()
                payload[name] = value
                with self.assertRaises(JobPostingAnalysisValidationError):
                    validate_analysis_response(json.dumps(payload), job_posting_id=JOB_ID)

    def test_alternatives_and_multi_category_evidence_remain_one_requirement(self) -> None:
        # Synthetic fixture already used by the offline Agent contract tests.
        source, payload = posting_fixture(), analysis_fixture()
        payload["qualifications"][0]["categories"] = ["skill", "experience"]
        validated = validate_analysis_response(json.dumps(payload), job_posting_id=JOB_ID)
        validate_analysis_content(validated, posting=source)
        row = JobAnalysisQualification(
            job_posting_id=UUID(JOB_ID), position=0, **validated["qualifications"][0]
        )
        self.assertEqual("Must have Python or Go.", row.value)
        self.assertEqual(["skill", "experience"], row.categories)
        self.assertEqual(validated["qualifications"][0]["evidence"], row.evidence)

    def test_supported_filter_and_single_requirement_queries_compile(self) -> None:
        statement = (
            select(JobPostingAnalysis.job_posting_id, JobPosting.title, JobPosting.company_name)
            .join(JobPosting, JobPosting.id == JobPostingAnalysis.job_posting_id)
            .where(JobPosting.closed_at.is_(None), JobPostingAnalysis.job_family == "ai_engineer",
                   JobPostingAnalysis.seniority == "intern")
        )
        sql = str(statement.compile(dialect=DIALECT, compile_kwargs={"literal_binds": True}))
        self.assertIn("JOIN job_postings ON job_postings.id = job_postings_analyses.job_posting_id", sql)
        self.assertIn("job_postings.closed_at IS NULL", sql)
        self.assertIn("job_postings.title", sql)
        self.assertIn("job_postings.company_name", sql)
        self.assertNotIn("is_open", sql)
        self.assertIn("job_postings_analyses.job_family = 'ai_engineer'", sql)
        detail = select(JobAnalysisQualification).where(JobAnalysisQualification.id == UUID(JOB_ID))
        self.assertIn("job_analysis_qualifications.id =", str(detail.compile(dialect=DIALECT)))
        self.assertEqual(
            [("job_family", "seniority")],
            [tuple(i.columns.keys()) for i in JobPostingAnalysis.__table__.indexes],
        )


class JobAnalysisMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
        cls.revision = cls.script.get_revision(REVISION)

    def render(self, direction: str):
        output = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": output, "literal_binds": True},
        )
        operations = Operations(context)
        created = {}
        original = operations.create_table

        def capture(name, *args, **kwargs):
            table = original(name, *args, **kwargs)
            created[name] = table
            return table

        # Any accidental connection attempt fails this test instead of reaching a service.
        with patch("sqlalchemy.create_engine", side_effect=AssertionError("No database access")), \
             patch.object(self.revision.module, "op", operations), \
             patch.object(operations, "create_table", side_effect=capture), \
             patch.object(operations, "create_index", wraps=operations.create_index) as indexes:
            getattr(self.revision.module, direction)()
        return output.getvalue(), created, indexes.call_args_list

    def test_single_head_follows_the_resume_migration(self) -> None:
        self.assertEqual([REVISION], self.script.get_heads())
        self.assertEqual(PARENT_REVISION, self.revision.down_revision)

    def test_upgrade_creates_exactly_the_six_agreed_tables(self) -> None:
        sql, created, _ = self.render("upgrade")
        self.assertEqual(set(TABLES), set(created))
        for forbidden in ("DROP TABLE", "ALTER TABLE users", "ALTER TABLE resumes", "INSERT INTO", "GRANT ", "CREATE POLICY"):
            self.assertNotIn(forbidden, sql)
        self.assertLess(sql.index("CREATE TABLE job_postings_analyses"), sql.index("CREATE TABLE job_analysis_locations"))

    def test_migration_columns_constraints_defaults_and_indexes_match_models(self) -> None:
        _, created, index_calls = self.render("upgrade")
        for name, table in TABLES.items():
            with self.subTest(table=name):
                self.assertEqual(table_signature(table), table_signature(created[name]))
        actual = {(call.args[0], call.args[1], tuple(call.args[2])) for call in index_calls}
        expected = {(i.name, name, tuple(i.columns.keys())) for name, t in TABLES.items() for i in t.indexes}
        self.assertEqual(expected, actual)

    def test_rls_is_enabled_on_every_new_table_without_open_access_policies(self) -> None:
        sql, _, _ = self.render("upgrade")
        for name in TABLES:
            with self.subTest(table=name):
                self.assertIn(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;", sql)
        self.assertNotIn("DISABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("CREATE POLICY", sql)

    def test_postgres_ddl_contains_identity_evidence_and_monetary_guards(self) -> None:
        sql, _, _ = self.render("upgrade")
        for rule in (
            "agent_version TEXT NOT NULL",
            "analyzed_at TIMESTAMP WITH TIME ZONE NOT NULL",
            "jsonb_array_length(evidence) > 0",
            "jsonb_array_length(role_overview_evidence) = 0",
            "minimum <= maximum", "minimum >= 0", "maximum >= 0",
            "'NaN'::numeric", "'Infinity'::numeric",
            "cardinality(categories) > 0", "array_position(categories, NULL) IS NULL",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, sql)
        self.assertEqual(6, sql.count("ON DELETE CASCADE"))

    def test_downgrade_drops_only_new_tables_children_before_parent(self) -> None:
        sql, _, _ = self.render("downgrade")
        drops = [line.removeprefix("DROP TABLE ").removesuffix(";") for line in sql.splitlines() if line.startswith("DROP TABLE ")]
        self.assertEqual(set(TABLES), set(drops))
        self.assertEqual("job_postings_analyses", drops[-1])
        self.assertNotIn("ALTER TABLE", sql)


if __name__ == "__main__":
    unittest.main()
