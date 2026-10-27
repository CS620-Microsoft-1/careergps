"""Create plan_items: resources a student saved to their action plan, per destination.

Revision ID: 3f8a1c6d2e90
Revises: 1a7c4e9b2d60

Replaces the per-user JSON files under backend/local_results/plans (app/services/plans.py).
resource_id is an id from data/resources.yaml, not a foreign key: the catalog is a file.
Schema only: no data copy. RLS follows the existing backend-only access model (Supabase Data API
disabled); no anonymous/authenticated policies. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "3f8a1c6d2e90"
down_revision = "1a7c4e9b2d60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('plan_items',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('job_family', sa.Text(), nullable=False),
    sa.Column('resource_id', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default=sa.text("'saved'"), nullable=False),
    sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')", name='ck_plan_items_job_family'),
    sa.CheckConstraint("status IN ('saved', 'done')", name='ck_plan_items_status'),
    sa.CheckConstraint("(status = 'done') = (done_at IS NOT NULL)", name='ck_plan_items_done_at'),
    sa.CheckConstraint("btrim(resource_id) <> ''", name='ck_plan_items_resource_id'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'job_family', 'resource_id')
    )

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE plan_items ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table('plan_items')
