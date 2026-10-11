"""add profiles, link users to supabase auth

Revision ID: 6786f26fc026
Revises: 8cb9c0fe6e22
Create Date: 2026-10-11 13:44:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6786f26fc026'
down_revision: Union[str, Sequence[str], None] = '8cb9c0fe6e22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('profiles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('target_role', sa.String(length=100), nullable=False),
    sa.Column('experience_level', sa.String(length=50), nullable=False),
    sa.Column('graduation_year', sa.SmallInteger(), nullable=False),
    sa.Column('university', sa.String(length=150), nullable=False),
    sa.Column('location', sa.String(length=100), nullable=True),
    sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.execute("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY")

    # Added by hand (autogenerate doesn't know Supabase's auth schema).
    # users.id is the Supabase Auth account id; deleting the account deletes our rows too.
    # Fails if users already has rows without a matching auth.users row (it was empty when written).
    op.create_foreign_key(
        'users_id_auth_users_fkey', 'users', 'users',
        ['id'], ['id'],
        referent_schema='auth', ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('users_id_auth_users_fkey', 'users', type_='foreignkey')
    op.drop_table('profiles')
