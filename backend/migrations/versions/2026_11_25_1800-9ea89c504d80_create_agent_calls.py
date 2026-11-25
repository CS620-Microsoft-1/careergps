"""Create agent_calls: latency, tokens and estimated cost of every Foundry Agent call.

Revision ID: 9ea89c504d80
Revises: 9aa1698efdd2

One row per responses.create, written by app.services.agent_calls. No prompts or answers are stored.
user_id references auth.users, not users: onboarding analyses a résumé before the users row exists.
ON DELETE CASCADE, so deleting an account (DELETE /me removes the Supabase Auth user) removes its
rows. run_id is the Skill Gap run id, without a foreign key, since local runs may not be saved to
skill_gap_runs.
Schema only: no data copy. RLS follows the backend-only access model (Supabase Data API disabled);
no anonymous/authenticated policies. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "9ea89c504d80"
down_revision = "9aa1698efdd2"
branch_labels = None
depends_on = None

_STATUSES = "('completed', 'incomplete', 'failed', 'cancelled', 'queued', 'in_progress', 'error', 'timeout')"


def upgrade() -> None:
    op.create_table('agent_calls',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('agent', sa.Text(), nullable=False),
    sa.Column('agent_version', sa.Text(), nullable=True),
    sa.Column('model', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('error_type', sa.Text(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('cached_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('reasoning_tokens', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True),
    sa.CheckConstraint(f"status IN {_STATUSES}", name='ck_agent_calls_status'),
    sa.CheckConstraint('latency_ms >= 0', name='ck_agent_calls_latency_ms'),
    sa.CheckConstraint('input_tokens >= 0 AND cached_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0',
                       name='ck_agent_calls_tokens'),
    sa.CheckConstraint('cost_usd >= 0', name='ck_agent_calls_cost_usd'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_calls_created_at', 'agent_calls', ['created_at'], unique=False)
    op.create_index('ix_agent_calls_agent_created_at', 'agent_calls', ['agent', 'created_at'], unique=False)
    op.create_index('ix_agent_calls_user_id', 'agent_calls', ['user_id'], unique=False)

    # Added by hand: auth is Supabase's schema, so this foreign key isn't in the models;
    # migrations/env.py keeps autogenerate from dropping it (see the users migration).
    op.execute(
        'ALTER TABLE agent_calls ADD CONSTRAINT fk_agent_calls_user '
        'FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE'
    )

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE agent_calls ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index('ix_agent_calls_user_id', table_name='agent_calls')
    op.drop_index('ix_agent_calls_agent_created_at', table_name='agent_calls')
    op.drop_index('ix_agent_calls_created_at', table_name='agent_calls')
    op.drop_table('agent_calls')
