"""Link each résumé to one destination (resumes.job_family).

Revision ID: 5b1e9c3f7a2d
Revises: 7d2c91a4e8b6

A destination is a target role with its own résumé: the newest resumes row for a job_family.
Additive only: users.active_resume_id stays, so code that doesn't know job_family keeps working.

Backfill: each user's active résumé is linked to their current target role. Older versions keep
job_family NULL (history, not linked to a destination). The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "5b1e9c3f7a2d"
down_revision = "7d2c91a4e8b6"
branch_labels = None
depends_on = None

_FAMILY_OF_ROLE = """CASE u.target_role
    WHEN 'Software Engineer' THEN 'software_engineer'
    WHEN 'Data Analyst' THEN 'data_analyst'
    WHEN 'AI Engineer' THEN 'ai_engineer'
END"""


def upgrade() -> None:
    op.add_column('resumes', sa.Column('job_family', sa.Text(), nullable=True))
    op.create_check_constraint(
        'ck_resumes_job_family', 'resumes', "job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')"
    )
    op.create_index(
        'ix_resumes_user_id_job_family_created_at', 'resumes', ['user_id', 'job_family', 'created_at'], unique=False
    )
    op.execute(
        f"UPDATE resumes AS r SET job_family = {_FAMILY_OF_ROLE} FROM users AS u WHERE u.active_resume_id = r.id"
    )


def downgrade() -> None:
    op.drop_index('ix_resumes_user_id_job_family_created_at', table_name='resumes')
    op.drop_constraint('ck_resumes_job_family', 'resumes', type_='check')
    op.drop_column('resumes', 'job_family')
