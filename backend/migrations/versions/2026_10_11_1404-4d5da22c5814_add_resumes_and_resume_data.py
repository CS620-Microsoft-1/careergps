"""add resumes and structured resume data

Revision ID: 4d5da22c5814
Revises: 6786f26fc026
Create Date: 2026-10-11 14:04:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4d5da22c5814'
down_revision: Union[str, Sequence[str], None] = '6786f26fc026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ('resumes', 'educations', 'experiences', 'skills', 'projects')


def _owner_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('resume_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def _owner_constraints() -> list[sa.Constraint]:
    return [
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resume_id'], ['resumes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('profiles', sa.Column('phone', sa.String(length=50), nullable=True))
    op.add_column('profiles', sa.Column('links', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table('resumes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_code', sa.String(length=50), nullable=True),
    sa.Column('extracted', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('parsed_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('parser_version', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )

    op.create_table('educations',
    *_owner_columns(),
    sa.Column('school', sa.String(length=200), nullable=False),
    sa.Column('degree', sa.String(length=200), nullable=True),
    sa.Column('field_of_study', sa.String(length=200), nullable=True),
    sa.Column('start_date', sa.String(length=7), nullable=True),
    sa.Column('end_date', sa.String(length=7), nullable=True),
    sa.Column('gpa', sa.String(length=20), nullable=True),
    *_owner_constraints()
    )

    op.create_table('experiences',
    *_owner_columns(),
    sa.Column('company', sa.String(length=200), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('start_date', sa.String(length=7), nullable=True),
    sa.Column('end_date', sa.String(length=7), nullable=True),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    *_owner_constraints()
    )

    op.create_table('skills',
    *_owner_columns(),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    *_owner_constraints()
    )
    op.create_index('skills_user_id_lower_name_key', 'skills', ['user_id', sa.text('lower(name)')], unique=True)

    op.create_table('projects',
    *_owner_columns(),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('technologies', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    *_owner_constraints()
    )

    for table in ('educations', 'experiences', 'projects'):
        op.create_index(f'ix_{table}_user_id', table, ['user_id'])
    op.create_index('ix_skills_user_id', 'skills', ['user_id'])

    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('projects', 'skills', 'experiences', 'educations', 'resumes'):
        op.drop_table(table)
    op.drop_column('profiles', 'links')
    op.drop_column('profiles', 'phone')
