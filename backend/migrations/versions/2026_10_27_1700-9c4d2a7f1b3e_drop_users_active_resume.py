"""Drop users.active_resume_id: users.target_role selects a destination, which names its résumé.

Revision ID: 9c4d2a7f1b3e
Revises: 6d7e2b9a4c15

Code before this point still moved the active résumé, so the selected role gets a destination from
it first, while the pointer still exists. An existing destination is kept: code from this point on
writes only destinations, so after it ships the pointer can be older than the destination.
The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "9c4d2a7f1b3e"
down_revision = "6d7e2b9a4c15"
branch_labels = None
depends_on = None

_FAMILY_OF_ROLE = """CASE u.target_role
    WHEN 'Software Engineer' THEN 'software_engineer'
    WHEN 'Data Analyst' THEN 'data_analyst'
    WHEN 'AI Engineer' THEN 'ai_engineer'
END"""


def upgrade() -> None:
    op.execute(
        f"""INSERT INTO destinations (user_id, job_family, resume_id)
        SELECT u.id, {_FAMILY_OF_ROLE}, u.active_resume_id FROM users AS u
        WHERE u.active_resume_id IS NOT NULL AND {_FAMILY_OF_ROLE} IS NOT NULL
        ON CONFLICT (user_id, job_family) DO NOTHING"""
    )
    op.drop_constraint('fk_users_active_resume', 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_active_resume_id'), table_name='users')
    op.drop_column('users', 'active_resume_id')


def downgrade() -> None:
    op.add_column('users', sa.Column('active_resume_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_users_active_resume_id'), 'users', ['active_resume_id'], unique=False)
    op.create_foreign_key(
        'fk_users_active_resume', 'users', 'resumes',
        ['active_resume_id', 'id'], ['id', 'user_id'],
        ondelete='SET NULL (active_resume_id)',
    )
    # The selected destination's résumé becomes the active one again.
    op.execute(
        f"""UPDATE users AS u SET active_resume_id = d.resume_id FROM destinations AS d
        WHERE d.user_id = u.id AND d.job_family = {_FAMILY_OF_ROLE}"""
    )
