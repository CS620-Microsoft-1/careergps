"""Create the catalog tables: certifications, school_courses, student_orgs and catalog_versions.

Revision ID: c9413046949c
Revises: 9c4d2a7f1b3e

Moves the certification catalog (data/certifications.json) and the school_course / student_org
entries of data/resources.yaml into the database. Ids are the existing slugs and never change;
rows are never deleted, only set to active = false.

Schema only: no data copy. Load the data with `python -m scripts.seed_catalog` after upgrading.
Until then the backend keeps reading the files. RLS follows the backend-only access model
(Supabase Data API disabled); no anonymous/authenticated policies. The database owner applies this
after merge.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9413046949c"
down_revision = "9c4d2a7f1b3e"
branch_labels = None
depends_on = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def _school_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('school', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('meta', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('last_verified', sa.Date(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table('certifications',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('cost_note', sa.Text(), nullable=False),
    sa.Column('level', sa.Text(), nullable=False),
    sa.Column('skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('last_verified', sa.Date(), nullable=False),
    *_common_columns(),
    sa.CheckConstraint("btrim(id) <> ''", name='ck_certifications_id'),
    sa.CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')", name='ck_certifications_level'),
    sa.CheckConstraint('cost_usd >= 0', name='ck_certifications_cost_usd'),
    sa.CheckConstraint("jsonb_typeof(skills) = 'object'", name='ck_certifications_skills'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_certifications_active_sort_order', 'certifications', ['active', 'sort_order'], unique=False)

    op.create_table('school_courses',
    *_school_columns(),
    *_common_columns(),
    sa.CheckConstraint("btrim(id) <> ''", name='ck_school_courses_id'),
    sa.CheckConstraint("jsonb_typeof(skills) = 'array'", name='ck_school_courses_skills'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_school_courses_school_active', 'school_courses', ['school', 'active'], unique=False)

    op.create_table('student_orgs',
    *_school_columns(),
    sa.Column('alongside', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    *_common_columns(),
    sa.CheckConstraint("btrim(id) <> ''", name='ck_student_orgs_id'),
    sa.CheckConstraint("jsonb_typeof(skills) = 'array'", name='ck_student_orgs_skills'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_student_orgs_school_active', 'student_orgs', ['school', 'active'], unique=False)

    op.create_table('catalog_versions',
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('version', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    for table in ('certifications', 'school_courses', 'student_orgs', 'catalog_versions'):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table('catalog_versions')
    op.drop_index('ix_student_orgs_school_active', table_name='student_orgs')
    op.drop_table('student_orgs')
    op.drop_index('ix_school_courses_school_active', table_name='school_courses')
    op.drop_table('school_courses')
    op.drop_index('ix_certifications_active_sort_order', table_name='certifications')
    op.drop_table('certifications')
