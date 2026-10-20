"""extend users and add resume tables

Revision ID: 02a858fed0df
Revises: 6ef2e4581bd9
Create Date: 2026-10-20 15:01:12.134747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '02a858fed0df'
down_revision: Union[str, Sequence[str], None] = '6ef2e4581bd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- users -----------------------------------------------------------------------------------
    # Rename by hand: autogenerate wrote this as drop email + add primary_email, which loses data.
    op.alter_column('users', 'email', new_column_name='primary_email')
    op.execute('ALTER TABLE users RENAME CONSTRAINT users_email_key TO users_primary_email_key')

    # NOT NULL columns without defaults: safe only because users has no rows (checked before this
    # migration; rows are created at the end of onboarding).
    op.add_column('users', sa.Column('first_name', sa.String(length=100), nullable=False))
    op.add_column('users', sa.Column('last_name', sa.String(length=100), nullable=False))
    op.add_column('users', sa.Column('target_role', sa.String(length=30), nullable=False))
    op.add_column('users', sa.Column('experience_level', sa.String(length=20), nullable=False))
    op.add_column('users', sa.Column('graduation_year', sa.SmallInteger(), nullable=False))
    op.add_column('users', sa.Column('university', sa.String(length=150), nullable=False))
    op.add_column('users', sa.Column('preferred_location', sa.String(length=100), nullable=False))
    op.add_column('users', sa.Column('resume_emails', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False))
    op.add_column('users', sa.Column('phones', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False))
    op.add_column('users', sa.Column('current_location', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('linkedin_url', sa.String(length=2048), nullable=True))
    op.add_column('users', sa.Column('github_url', sa.String(length=2048), nullable=True))
    op.add_column('users', sa.Column('website_url', sa.String(length=2048), nullable=True))
    op.add_column('users', sa.Column('active_resume_id', sa.Uuid(), nullable=True))
    op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=False))
    op.alter_column('users', 'full_name', existing_type=sa.VARCHAR(length=255), nullable=True)
    op.create_index(op.f('ix_users_active_resume_id'), 'users', ['active_resume_id'], unique=False)

    # Added by hand: autogenerate doesn't detect CHECK constraints on an existing table.
    op.create_check_constraint('ck_users_primary_email_lowercase', 'users', 'primary_email = lower(primary_email)')
    op.create_check_constraint('ck_users_graduation_year_range', 'users', 'graduation_year BETWEEN 2000 AND 2100')

    # Added by hand: users.id is the Supabase Auth account id. auth is Supabase's schema, so this
    # foreign key isn't in the models; migrations/env.py keeps autogenerate from dropping it.
    op.execute(
        'ALTER TABLE users ADD CONSTRAINT users_id_fkey '
        'FOREIGN KEY (id) REFERENCES auth.users (id) ON DELETE CASCADE'
    )

    # --- resume tables -------------------------------------------------------------------------
    op.create_table('resumes',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=True),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('file_type', sa.String(length=10), nullable=False),
    sa.Column('parser', sa.String(length=50), nullable=False),
    sa.Column('ocr_pages', postgresql.ARRAY(sa.Integer()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('agent_name', sa.String(length=255), nullable=False),
    sa.Column('schema_version', sa.String(length=20), nullable=False),
    sa.Column('confirmed_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("file_type IN ('pdf', 'docx')", name='ck_resumes_file_type'),
    sa.CheckConstraint("jsonb_typeof(confirmed_data) = 'object'", name='ck_resumes_confirmed_data_object'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_resumes_id_user_id')
    )
    op.create_index('ix_resumes_user_id_created_at', 'resumes', ['user_id', 'created_at'], unique=False)
    op.create_table('resume_achievements',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('issuer', sa.String(length=255), nullable=True),
    sa.Column('url', sa.String(length=2048), nullable=True),
    sa.Column('content', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('issued_date', sa.String(length=50), nullable=True),
    sa.Column('issued_month', sa.Date(), nullable=True),
    sa.Column('date_precision', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("date_precision IN ('month', 'year')", name='ck_resume_achievements_date_precision'),
    sa.CheckConstraint("kind = 'certification' OR url IS NULL", name='ck_resume_achievements_url'),
    sa.CheckConstraint("kind IN ('certification', 'award')", name='ck_resume_achievements_kind'),
    sa.CheckConstraint('position >= 0', name='ck_resume_achievements_position'),
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'], name='fk_resume_achievements_resume', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resume_id', 'kind', 'position', name='uq_resume_achievements_position')
    )
    op.create_index(op.f('ix_resume_achievements_user_id'), 'resume_achievements', ['user_id'], unique=False)
    op.create_table('resume_educations',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('institution', sa.String(length=255), nullable=True),
    sa.Column('degree', sa.String(length=255), nullable=True),
    sa.Column('major', sa.String(length=255), nullable=True),
    sa.Column('gpa', sa.String(length=20), nullable=True),
    sa.Column('content', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('start_date', sa.String(length=20), nullable=True),
    sa.Column('end_date', sa.String(length=20), nullable=True),
    sa.Column('degree_level', sa.String(length=20), nullable=True),
    sa.Column('gpa_value', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('gpa_scale', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('start_month', sa.Date(), nullable=True),
    sa.Column('end_month', sa.Date(), nullable=True),
    sa.Column('date_precision', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("date_precision IN ('month', 'year')", name='ck_resume_educations_date_precision'),
    sa.CheckConstraint("degree_level IN ('associate', 'bachelor', 'master', 'doctorate', 'other')", name='ck_resume_educations_degree_level'),
    sa.CheckConstraint('gpa_scale > 0', name='ck_resume_educations_gpa_scale'),
    sa.CheckConstraint('gpa_value >= 0', name='ck_resume_educations_gpa_value'),
    sa.CheckConstraint('institution IS NOT NULL OR degree IS NOT NULL OR major IS NOT NULL', name='ck_resume_educations_not_blank'),
    sa.CheckConstraint('position >= 0', name='ck_resume_educations_position'),
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'], name='fk_resume_educations_resume', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resume_id', 'position', name='uq_resume_educations_position')
    )
    op.create_index(op.f('ix_resume_educations_user_id'), 'resume_educations', ['user_id'], unique=False)
    op.create_table('resume_experiences',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('organization', sa.String(length=255), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('content', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('start_date', sa.String(length=20), nullable=True),
    sa.Column('end_date', sa.String(length=20), nullable=True),
    sa.Column('start_month', sa.Date(), nullable=True),
    sa.Column('end_month', sa.Date(), nullable=True),
    sa.Column('date_precision', sa.String(length=10), nullable=True),
    sa.Column('is_current', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("date_precision IN ('month', 'year')", name='ck_resume_experiences_date_precision'),
    sa.CheckConstraint("kind IN ('work', 'research', 'leadership')", name='ck_resume_experiences_kind'),
    sa.CheckConstraint('organization IS NOT NULL OR title IS NOT NULL OR cardinality(content) > 0', name='ck_resume_experiences_not_blank'),
    sa.CheckConstraint('position >= 0', name='ck_resume_experiences_position'),
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'], name='fk_resume_experiences_resume', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resume_id', 'kind', 'position', name='uq_resume_experiences_position')
    )
    op.create_index(op.f('ix_resume_experiences_user_id'), 'resume_experiences', ['user_id'], unique=False)
    op.create_table('resume_projects',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('url', sa.String(length=2048), nullable=True),
    sa.Column('technologies', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('content', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('name IS NOT NULL OR cardinality(content) > 0', name='ck_resume_projects_not_blank'),
    sa.CheckConstraint('position >= 0', name='ck_resume_projects_position'),
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'], name='fk_resume_projects_resume', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resume_id', 'position', name='uq_resume_projects_position')
    )
    op.create_index(op.f('ix_resume_projects_user_id'), 'resume_projects', ['user_id'], unique=False)
    op.create_table('resume_skills',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('resume_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('normalized_name', sa.String(length=100), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('source_project_id', sa.Uuid(), nullable=True),
    sa.Column('source_achievement_id', sa.Uuid(), nullable=True),
    sa.Column('source_experience_id', sa.Uuid(), nullable=True),
    sa.Column('source_education_id', sa.Uuid(), nullable=True),
    sa.Column('evidence_text', sa.Text(), nullable=True),
    sa.Column('position', sa.SmallInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("num_nonnulls(source_project_id, source_achievement_id, source_experience_id, source_education_id) = CASE WHEN source = 'listed' THEN 0 ELSE 1 END AND (source <> 'project' OR source_project_id IS NOT NULL) AND (source <> 'certification' OR source_achievement_id IS NOT NULL) AND (source <> 'experience' OR source_experience_id IS NOT NULL) AND (source <> 'education' OR source_education_id IS NOT NULL)", name='ck_resume_skills_source_link'),
    sa.CheckConstraint("position IS NULL OR (source = 'listed' AND position >= 0)", name='ck_resume_skills_position'),
    sa.CheckConstraint("source IN ('listed', 'project', 'certification', 'experience', 'education')", name='ck_resume_skills_source'),
    sa.ForeignKeyConstraint(['resume_id', 'user_id'], ['resumes.id', 'resumes.user_id'], name='fk_resume_skills_resume', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_achievement_id'], ['resume_achievements.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_education_id'], ['resume_educations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_experience_id'], ['resume_experiences.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_project_id'], ['resume_projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resume_id', 'normalized_name', 'source', 'source_project_id', 'source_achievement_id', 'source_experience_id', 'source_education_id', name='uq_resume_skills_evidence', postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_resume_skills_user_id'), 'resume_skills', ['user_id'], unique=False)

    # --- users -> resumes ----------------------------------------------------------------------
    # Last, because users and resumes reference each other. Deleting the active résumé clears only
    # the pointer (SET NULL on one column of the composite key needs Postgres 15+).
    op.create_foreign_key(
        'fk_users_active_resume', 'users', 'resumes',
        ['active_resume_id', 'id'], ['id', 'user_id'],
        ondelete='SET NULL (active_resume_id)',
    )

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE resumes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resume_achievements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resume_educations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resume_experiences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resume_projects ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE resume_skills ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema. Fails if users has rows with no full_name; the shared DB rules apply."""
    op.drop_constraint('fk_users_active_resume', 'users', type_='foreignkey')

    # Dropping a table also drops its RLS setting.
    op.drop_index(op.f('ix_resume_skills_user_id'), table_name='resume_skills')
    op.drop_table('resume_skills')
    op.drop_index(op.f('ix_resume_projects_user_id'), table_name='resume_projects')
    op.drop_table('resume_projects')
    op.drop_index(op.f('ix_resume_experiences_user_id'), table_name='resume_experiences')
    op.drop_table('resume_experiences')
    op.drop_index(op.f('ix_resume_educations_user_id'), table_name='resume_educations')
    op.drop_table('resume_educations')
    op.drop_index(op.f('ix_resume_achievements_user_id'), table_name='resume_achievements')
    op.drop_table('resume_achievements')
    op.drop_index('ix_resumes_user_id_created_at', table_name='resumes')
    op.drop_table('resumes')

    op.execute('ALTER TABLE users DROP CONSTRAINT users_id_fkey')
    op.drop_constraint('ck_users_graduation_year_range', 'users', type_='check')
    op.drop_constraint('ck_users_primary_email_lowercase', 'users', type_='check')
    op.drop_index(op.f('ix_users_active_resume_id'), table_name='users')
    op.alter_column('users', 'full_name', existing_type=sa.VARCHAR(length=255), nullable=False)
    op.drop_column('users', 'terms_accepted_at')
    op.drop_column('users', 'active_resume_id')
    op.drop_column('users', 'website_url')
    op.drop_column('users', 'github_url')
    op.drop_column('users', 'linkedin_url')
    op.drop_column('users', 'current_location')
    op.drop_column('users', 'phones')
    op.drop_column('users', 'resume_emails')
    op.drop_column('users', 'preferred_location')
    op.drop_column('users', 'university')
    op.drop_column('users', 'graduation_year')
    op.drop_column('users', 'experience_level')
    op.drop_column('users', 'target_role')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
    op.execute('ALTER TABLE users RENAME CONSTRAINT users_primary_email_key TO users_email_key')
    op.alter_column('users', 'primary_email', new_column_name='email')
