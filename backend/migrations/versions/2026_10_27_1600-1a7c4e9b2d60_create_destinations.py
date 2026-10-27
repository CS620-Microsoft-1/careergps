"""Create destinations: each target role a student works toward, and the résumé it uses.

Revision ID: 1a7c4e9b2d60
Revises: 7d2c91a4e8b6

One row per (user, job family) with a resume_id; several roles may use the same résumé.
Additive only: users.active_resume_id stays, so current code keeps working.

Backfill: one destination per user, for their current target role and active résumé.
RLS follows the backend-only access model (Supabase Data API disabled); no anonymous/authenticated
policies. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "1a7c4e9b2d60"
down_revision = "7d2c91a4e8b6"
branch_labels = None
depends_on = None

_FAMILY_OF_ROLE = """CASE u.target_role
    WHEN 'Software Engineer' THEN 'software_engineer'
    WHEN 'Data Analyst' THEN 'data_analyst'
    WHEN 'AI Engineer' THEN 'ai_engineer'
END"""


def upgrade() -> None:
    op.create_table('destinations',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('job_family', sa.Text(), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')", name='ck_destinations_job_family'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    # The résumé must belong to the same user. A résumé a role uses can't be deleted.
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'], name='fk_destinations_resume'),
    sa.PrimaryKeyConstraint('user_id', 'job_family')
    )
    op.create_index('ix_destinations_resume_id', 'destinations', ['resume_id'], unique=False)
    op.execute(
        f"""INSERT INTO destinations (user_id, job_family, resume_id)
        SELECT u.id, {_FAMILY_OF_ROLE}, u.active_resume_id FROM users AS u
        WHERE u.active_resume_id IS NOT NULL AND {_FAMILY_OF_ROLE} IS NOT NULL"""
    )

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE destinations ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index('ix_destinations_resume_id', table_name='destinations')
    op.drop_table('destinations')
