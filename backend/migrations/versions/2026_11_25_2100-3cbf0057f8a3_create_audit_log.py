"""Create audit_log (one row per data write) and the audit_events view (writes and Agent calls).

Revision ID: 3cbf0057f8a3
Revises: 9ea89c504d80

audit_log is written by app.services.audit in the same transaction as the write it describes
(the plan's local JSON files are the exception: their row is written separately). details holds
ids, statuses, counts and changed field names, never résumé content or field values.

user_id is the student whose data changed. It references auth.users (as agent_calls does) with
ON DELETE CASCADE, so deleting an account removes its records. Catalog and ingest records have no
user.

audit_events shows audit_log and agent_calls as one timeline. security_invoker, so the view
never reads with more rights than the caller.
Schema only: no data copy. RLS follows the backend-only access model (Supabase Data API disabled);
no anonymous/authenticated policies. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "3cbf0057f8a3"
down_revision = "9ea89c504d80"
branch_labels = None
depends_on = None

AUDIT_EVENTS_VIEW = """
CREATE VIEW audit_events WITH (security_invoker = true) AS
SELECT created_at AS occurred_at, user_id, 'data_write'::text AS kind, source, action,
       target_type, target_id, NULL::text AS status, details
FROM audit_log
UNION ALL
-- An Agent call with a user came from a signed-in request; without one, the source isn't recorded.
SELECT created_at, user_id, 'agent_call', CASE WHEN user_id IS NOT NULL THEN 'api' END,
       'agent.called', 'agent', agent, status,
       jsonb_strip_nulls(jsonb_build_object(
           'agent_version', agent_version, 'model', model, 'run_id', run_id, 'error_type', error_type,
           'latency_ms', latency_ms, 'input_tokens', input_tokens, 'output_tokens', output_tokens,
           'cost_usd', cost_usd))
FROM agent_calls
"""


def upgrade() -> None:
    op.create_table('audit_log',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=True),
    sa.Column('target_id', sa.Text(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"),
              nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.CheckConstraint("source IN ('api', 'script')", name='ck_audit_log_source'),
    sa.CheckConstraint("jsonb_typeof(details) = 'object'", name='ck_audit_log_details_object'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'], unique=False)
    op.create_index('ix_audit_log_user_id_created_at', 'audit_log', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_audit_log_action', 'audit_log', ['action'], unique=False)

    # Added by hand: auth is Supabase's schema, so this foreign key isn't in the models;
    # migrations/env.py keeps autogenerate from dropping it (see the users migration).
    op.execute(
        'ALTER TABLE audit_log ADD CONSTRAINT fk_audit_log_user '
        'FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE'
    )

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")

    op.execute(AUDIT_EVENTS_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW audit_events")
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_index('ix_audit_log_user_id_created_at', table_name='audit_log')
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_table('audit_log')
