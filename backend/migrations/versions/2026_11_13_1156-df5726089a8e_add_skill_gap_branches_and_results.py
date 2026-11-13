"""Store three-group Skill Gap runs: new run columns, skill_gap_run_branches and skill_gap_results.

Revision ID: df5726089a8e
Revises: c9413046949c

Follows docs/contracts/skill-gap-run-storage.schema.json v3. skill_gap_runs (6d7e2b9a4c15) had no place
for the three skill-group Agents, so this adds the run fields v3 needs, one row per Agent group
(skill_gap_run_branches, with its raw answer) and one row per core skill (skill_gap_results, with its
scores and quoted evidence). skill_gap_runs.report keeps the full v12 report the API returns;
skill_gap_results is its queryable copy, written once in the same transaction.

skill_gap_runs is empty, so the new NOT NULL columns need no backfill. Schema only: no data copy.
RLS follows the backend-only access model; no anonymous/authenticated policies. The database owner
applies this after merge.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "df5726089a8e"
down_revision = "c9413046949c"
branch_labels = None
depends_on = None

_SHA256 = "~ '^[0-9a-f]{64}$'"
_GROUPS = "('foundation', 'lifecycle', 'systems')"
_STORAGE_VERSIONS = ("('careergps.skill_gap_run_storage.v1', 'careergps.skill_gap_run_storage.v2', "
                     "'careergps.skill_gap_run_storage.v3')")


def _run_columns() -> list[sa.Column]:
    """Columns added to skill_gap_runs, in order; fresh objects so the migration can render twice."""
    return [
        sa.Column('storage_schema_version', sa.Text(),
                  server_default=sa.text("'careergps.skill_gap_run_storage.v3'"), nullable=False),
        sa.Column('resume_filename', sa.Text(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extraction_strategy', sa.Text(), nullable=True),
        sa.Column('partition_policy_version', sa.Text(), nullable=True),
        sa.Column('selection_policy_version', sa.Text(), nullable=True),
        sa.Column('reuse_from_run_id', sa.Uuid(), nullable=True),
        sa.Column('match_score', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('scored_skill_count', sa.SmallInteger(), nullable=True),
        sa.Column('unscored_skill_count', sa.SmallInteger(), nullable=True),
        sa.Column('extraction_audit', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('timings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
    ]


_RUN_CHECKS = [
    ('ck_skill_gap_runs_storage_schema_version', f"storage_schema_version IN {_STORAGE_VERSIONS}"),
    ('ck_skill_gap_runs_extraction_strategy', "extraction_strategy IN ('single', 'skill_groups')"),
    ('ck_skill_gap_runs_match_score', "match_score >= 0 AND match_score <= 1"),
    ('ck_skill_gap_runs_skill_counts', "scored_skill_count >= 0 AND unscored_skill_count >= 0"),
    ('ck_skill_gap_runs_extraction_audit_object', "jsonb_typeof(extraction_audit) = 'object'"),
    ('ck_skill_gap_runs_timings_object', "jsonb_typeof(timings) = 'object'"),
    # Only a finished analysis has a match score.
    ('ck_skill_gap_runs_match_when_completed', "status = 'completed' OR match_score IS NULL"),
    # A completed group run has its counts and merge audit (v3); older versions may not.
    ('ck_skill_gap_runs_v3_completed',
     "storage_schema_version <> 'careergps.skill_gap_run_storage.v3' OR status <> 'completed' OR "
     "(scored_skill_count IS NOT NULL AND unscored_skill_count IS NOT NULL AND extraction_audit IS NOT NULL)"),
]


def upgrade() -> None:
    for column in _run_columns():
        op.add_column('skill_gap_runs', column)
    for name, condition in _RUN_CHECKS:
        op.create_check_constraint(name, 'skill_gap_runs', condition)
    op.create_foreign_key('fk_skill_gap_runs_reuse_from_run', 'skill_gap_runs', 'skill_gap_runs',
                          ['reuse_from_run_id'], ['id'], ondelete='SET NULL')
    # Lets result rows prove they copy their run's owner and job family.
    op.create_unique_constraint('uq_skill_gap_runs_id_user_family', 'skill_gap_runs',
                                ['id', 'user_id', 'job_family'])

    op.create_table('skill_gap_run_branches',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('branch', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('agent_name', sa.Text(), nullable=True),
    sa.Column('agent_version', sa.Text(), nullable=True),
    sa.Column('model', sa.Text(), nullable=True),
    sa.Column('reasoning_effort', sa.Text(), nullable=True),
    # Hash of the exact group input; a later branch cache looks completed answers up by it.
    sa.Column('input_sha256', sa.Text(), nullable=True),
    sa.Column('reused', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_run_id', sa.Uuid(), nullable=True),
    sa.Column('model_calls', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('elapsed_seconds', sa.Float(), server_default=sa.text('0'), nullable=False),
    sa.Column('inference_seconds', sa.Float(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('cached_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('reasoning_tokens', sa.Integer(), nullable=True),
    sa.Column('error_code', sa.Text(), nullable=True),
    sa.Column('raw_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('validation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('response_processing', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(f"branch IN {_GROUPS}", name='ck_skill_gap_run_branches_branch'),
    sa.CheckConstraint("status IN ('pending', 'ready', 'running', 'completed', 'failed', 'skipped_empty', "
                       "'not_started')", name='ck_skill_gap_run_branches_status'),
    sa.CheckConstraint(f"input_sha256 {_SHA256}", name='ck_skill_gap_run_branches_input_sha256'),
    sa.CheckConstraint('model_calls >= 0 AND model_calls <= 1', name='ck_skill_gap_run_branches_model_calls'),
    sa.CheckConstraint('elapsed_seconds >= 0 AND inference_seconds >= 0',
                       name='ck_skill_gap_run_branches_seconds'),
    sa.CheckConstraint('input_tokens >= 0 AND cached_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0',
                       name='ck_skill_gap_run_branches_tokens'),
    sa.CheckConstraint("jsonb_typeof(validation) = 'object' AND jsonb_typeof(response_processing) = 'object'",
                       name='ck_skill_gap_run_branches_checks_objects'),
    sa.ForeignKeyConstraint(['run_id'], ['skill_gap_runs.id'],
                            name='fk_skill_gap_run_branches_run', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_run_id'], ['skill_gap_runs.id'],
                            name='fk_skill_gap_run_branches_source_run', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('run_id', 'branch')
    )
    op.create_index('ix_skill_gap_run_branches_input_sha256', 'skill_gap_run_branches', ['input_sha256'],
                    unique=False)

    op.create_table('skill_gap_results',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('skill_id', sa.Text(), nullable=False),
    # Copied from the run (enforced by the composite FK) so queries across users need no join.
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('job_family', sa.Text(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('skill_name', sa.Text(), nullable=False),
    sa.Column('module_id', sa.Text(), nullable=False),
    sa.Column('module_name', sa.Text(), nullable=False),
    sa.Column('branch', sa.Text(), nullable=True),
    sa.Column('evidence_kind', sa.Text(), nullable=False),
    sa.Column('calculation_state', sa.Text(), nullable=False),
    sa.Column('evidence_strength', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('skill_gap', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('grade', sa.Text(), nullable=True),
    sa.Column('demand_required_count', sa.Integer(), nullable=False),
    sa.Column('demand_preferred_only_count', sa.Integer(), nullable=False),
    sa.Column('demand_unspecified_count', sa.Integer(), nullable=False),
    sa.Column('demand_n', sa.Integer(), nullable=False),
    sa.Column('demand_weight', sa.Numeric(precision=7, scale=6), nullable=False),
    sa.Column('priority', sa.Numeric(precision=7, scale=6), nullable=True),
    sa.Column('priority_rank', sa.SmallInteger(), nullable=True),
    sa.Column('agent_assessment', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('original_agent_assessment', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('scoring_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('reference_check', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('merge_audit', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    # One item per quoted proof: role, unit_id, activity_id, source_path, quote, start, end.
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"),
              nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')",
                       name='ck_skill_gap_results_job_family'),
    sa.CheckConstraint('position >= 0', name='ck_skill_gap_results_position'),
    sa.CheckConstraint(f"branch IN {_GROUPS}", name='ck_skill_gap_results_branch'),
    sa.CheckConstraint("evidence_kind IN ('absent', 'knowledge', 'practice', 'limited_practice', 'uncertain')",
                       name='ck_skill_gap_results_evidence_kind'),
    sa.CheckConstraint("calculation_state IN ('scored', 'needs_confirmation')",
                       name='ck_skill_gap_results_calculation_state'),
    sa.CheckConstraint('evidence_strength >= 0 AND evidence_strength <= 1 AND skill_gap >= 0 AND skill_gap <= 1',
                       name='ck_skill_gap_results_scores'),
    sa.CheckConstraint("grade IN ('A', 'A-', 'B+', 'B', 'C', 'D', 'F')", name='ck_skill_gap_results_grade'),
    sa.CheckConstraint('demand_required_count >= 0 AND demand_preferred_only_count >= 0 AND '
                       'demand_unspecified_count >= 0 AND demand_n > 0', name='ck_skill_gap_results_demand'),
    sa.CheckConstraint('demand_weight >= 0 AND demand_weight <= 1 AND priority >= 0 AND priority <= 1',
                       name='ck_skill_gap_results_weights'),
    sa.CheckConstraint('priority_rank >= 1', name='ck_skill_gap_results_priority_rank'),
    # A scored skill has all its numbers; one that needs confirmation has none and no rank.
    sa.CheckConstraint(
        "CASE WHEN calculation_state = 'scored' THEN evidence_strength IS NOT NULL AND skill_gap IS NOT NULL "
        "AND grade IS NOT NULL AND priority IS NOT NULL ELSE evidence_strength IS NULL AND skill_gap IS NULL "
        "AND grade IS NULL AND priority IS NULL AND priority_rank IS NULL END",
        name='ck_skill_gap_results_scored_values'),
    sa.CheckConstraint("jsonb_typeof(agent_assessment) = 'object' AND jsonb_typeof(scoring_breakdown) = 'object' "
                       "AND jsonb_typeof(reference_check) = 'object' AND jsonb_typeof(merge_audit) = 'object'",
                       name='ck_skill_gap_results_details_objects'),
    sa.CheckConstraint("jsonb_typeof(evidence) = 'array'", name='ck_skill_gap_results_evidence_array'),
    # The run's owner and job family; deleting the run (or its résumé) deletes its results.
    sa.ForeignKeyConstraint(['run_id', 'user_id', 'job_family'],
                            ['skill_gap_runs.id', 'skill_gap_runs.user_id', 'skill_gap_runs.job_family'],
                            name='fk_skill_gap_results_run', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('run_id', 'skill_id'),
    sa.UniqueConstraint('run_id', 'position', name='uq_skill_gap_results_position'),
    sa.UniqueConstraint('run_id', 'priority_rank', name='uq_skill_gap_results_priority_rank')
    )
    # Other agents and analytics: one skill across a user's runs or across users of a role.
    op.create_index('ix_skill_gap_results_user_family_skill', 'skill_gap_results',
                    ['user_id', 'job_family', 'skill_id'], unique=False)

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE skill_gap_run_branches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE skill_gap_results ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index('ix_skill_gap_results_user_family_skill', table_name='skill_gap_results')
    op.drop_table('skill_gap_results')
    op.drop_index('ix_skill_gap_run_branches_input_sha256', table_name='skill_gap_run_branches')
    op.drop_table('skill_gap_run_branches')
    op.drop_constraint('uq_skill_gap_runs_id_user_family', 'skill_gap_runs', type_='unique')
    op.drop_constraint('fk_skill_gap_runs_reuse_from_run', 'skill_gap_runs', type_='foreignkey')
    for name, _ in reversed(_RUN_CHECKS):
        op.drop_constraint(name, 'skill_gap_runs', type_='check')
    for column in reversed(_run_columns()):
        op.drop_column('skill_gap_runs', column.name)
