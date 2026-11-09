"""Add course_code, credits and last_taught to school_courses.

Revision ID: e93b20128bb7
Revises: c9413046949c

Filled from the UW–Madison course guide by `python -m scripts.seed_catalog`. All three are
nullable: courses added by hand may not have them. Prerequisites are deliberately not stored.
Schema only: no data copy. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "e93b20128bb7"
down_revision = "c9413046949c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "COMP SCI 400"; cross-listed courses keep the guide's form, e.g. "COMP SCI/E C E 552".
    op.add_column('school_courses', sa.Column('course_code', sa.Text(), nullable=True))
    # The guide's text: "3", "1-3".
    op.add_column('school_courses', sa.Column('credits', sa.Text(), nullable=True))
    # The guide's text: "Fall 2025".
    op.add_column('school_courses', sa.Column('last_taught', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('school_courses', 'last_taught')
    op.drop_column('school_courses', 'credits')
    op.drop_column('school_courses', 'course_code')
