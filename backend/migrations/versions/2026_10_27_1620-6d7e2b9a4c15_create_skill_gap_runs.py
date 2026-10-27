"""Create skill_gap_runs: one Skill Gap analysis of one résumé for one job family.

Revision ID: 6d7e2b9a4c15
Revises: 3f8a1c6d2e90

Replaces the run folders under backend/local_results/web_skill_gaps (app/services/skill_gaps/runs.py),
following docs/contracts/skill-gap-run-storage.schema.json. Scores, quotations and pending states stay
in `report`; the immutable input is `reviewed_resume_snapshot`. Configuration columns that older local
runs didn't record are nullable so they can be imported.

Reuse rule as in the local queue: at most one queued/running run per (user, résumé, job family,
calculation fingerprint); finished runs may repeat (force). Schema only: no data copy. RLS follows the
backend-only access model; no anonymous/authenticated policies. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6d7e2b9a4c15"
down_revision = "3f8a1c6d2e90"
branch_labels = None
depends_on = None

_SHA256 = "~ '^[0-9a-f]{64}$'"


def upgrade() -> None:
    op.create_table('skill_gap_runs',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('job_family', sa.Text(), nullable=False),
    sa.Column('resume_hash', sa.Text(), nullable=False),
    sa.Column('reviewed_resume_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    # Configuration the result depends on; a change means the run is not reused.
    sa.Column('calculation_fingerprint', sa.Text(), nullable=False),
    sa.Column('demand_snapshot_fingerprint', sa.Text(), nullable=False),
    sa.Column('policy_version', sa.Text(), nullable=False),
    sa.Column('response_schema_name', sa.Text(), nullable=False),
    sa.Column('catalog_version', sa.Text(), nullable=True),
    sa.Column('prompt_revision', sa.Text(), nullable=True),
    sa.Column('instructions_sha256', sa.Text(), nullable=True),
    sa.Column('response_processing_version', sa.Text(), nullable=True),
    sa.Column('agent_name', sa.Text(), nullable=True),
    sa.Column('agent_version', sa.Text(), nullable=True),
    # Progress and outcome.
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('phase', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('elapsed_seconds', sa.Float(), server_default=sa.text('0'), nullable=False),
    sa.Column('model_calls', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('error_code', sa.Text(), nullable=True),
    sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('raw_agent_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint("job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')", name='ck_skill_gap_runs_job_family'),
    sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name='ck_skill_gap_runs_status'),
    sa.CheckConstraint(f"resume_hash {_SHA256}", name='ck_skill_gap_runs_resume_hash'),
    sa.CheckConstraint(f"calculation_fingerprint {_SHA256}", name='ck_skill_gap_runs_calculation_fingerprint'),
    sa.CheckConstraint(f"demand_snapshot_fingerprint {_SHA256}", name='ck_skill_gap_runs_demand_fingerprint'),
    sa.CheckConstraint(f"instructions_sha256 IS NULL OR instructions_sha256 {_SHA256}", name='ck_skill_gap_runs_instructions_sha256'),
    sa.CheckConstraint("jsonb_typeof(reviewed_resume_snapshot) = 'object'", name='ck_skill_gap_runs_snapshot_object'),
    sa.CheckConstraint('elapsed_seconds >= 0', name='ck_skill_gap_runs_elapsed_seconds'),
    sa.CheckConstraint('model_calls >= 0', name='ck_skill_gap_runs_model_calls'),
    # A completed run has its report and finish time; any other run has no report.
    sa.CheckConstraint(
        "CASE WHEN status = 'completed' THEN report IS NOT NULL AND jsonb_typeof(report) = 'object' "
        "AND completed_at IS NOT NULL AND error IS NULL ELSE report IS NULL END",
        name='ck_skill_gap_runs_completed_report'),
    sa.CheckConstraint("status IN ('queued', 'running') OR completed_at IS NOT NULL", name='ck_skill_gap_runs_completed_at'),
    # The résumé must belong to the same user; deleting it deletes its analyses.
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'],
                            name='fk_skill_gap_runs_resume', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # Latest run for a destination's résumé and configuration.
    op.create_index('ix_skill_gap_runs_latest', 'skill_gap_runs',
                    ['user_id', 'resume_id', 'job_family', 'calculation_fingerprint', 'created_at'], unique=False)
    op.create_index('ix_skill_gap_runs_user_id', 'skill_gap_runs', ['user_id'], unique=False)
    op.create_index('uq_skill_gap_runs_one_active', 'skill_gap_runs',
                    ['user_id', 'resume_id', 'job_family', 'calculation_fingerprint'], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE skill_gap_runs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index('uq_skill_gap_runs_one_active', table_name='skill_gap_runs')
    op.drop_index('ix_skill_gap_runs_user_id', table_name='skill_gap_runs')
    op.drop_index('ix_skill_gap_runs_latest', table_name='skill_gap_runs')
    op.drop_table('skill_gap_runs')
