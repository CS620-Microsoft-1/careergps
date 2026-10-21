"""Add current job posting analyses and five ordered detail tables.

Revision ID: 7d2c91a4e8b6
Revises: 02a858fed0df

Schema only: no backfill, remote calls, grants, or activation of JD persistence.
The database owner applies this after merge. RLS follows the existing backend-only
access model (Supabase Data API disabled); no anonymous/authenticated write policies.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7d2c91a4e8b6"
down_revision = "02a858fed0df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('job_postings_analyses',
    sa.Column('job_posting_id', sa.Uuid(), nullable=False),
    sa.Column('source', sa.Text(), nullable=True),
    sa.Column('external_id', sa.Text(), nullable=True),
    sa.Column('company_slug', sa.Text(), nullable=True),
    sa.Column('company_name', sa.Text(), nullable=True),
    sa.Column('company_tier', sa.Text(), nullable=True),
    sa.Column('job_title', sa.Text(), nullable=True),
    sa.Column('job_family', sa.Text(), nullable=True),
    sa.Column('seniority', sa.Text(), nullable=True),
    sa.Column('department', sa.Text(), nullable=True),
    sa.Column('role_overview', sa.Text(), nullable=True),
    sa.Column('role_overview_evidence', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('benefits', sa.Text(), nullable=True),
    sa.Column('other_relevant_information', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('salary_currency', sa.Text(), nullable=True),
    sa.Column('salary_interval', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_content_hash', sa.Text(), nullable=True),
    sa.Column('source_created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
    # Temporary placeholder; no availability check or source-table update.
    sa.Column('is_open', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("CASE WHEN jsonb_typeof(role_overview_evidence) = 'array' THEN CASE WHEN role_overview IS NULL THEN jsonb_array_length(role_overview_evidence) = 0 ELSE btrim(role_overview) <> '' AND jsonb_array_length(role_overview_evidence) > 0 END ELSE false END", name='ck_jpa_overview_evidence'),
    sa.CheckConstraint("job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')", name='ck_jpa_job_family'),
    sa.CheckConstraint("salary_interval IN ('hour', 'day', 'week', 'month', 'year', 'one_time')", name='ck_jpa_salary_interval'),
    sa.CheckConstraint("seniority IN ('intern', 'new_grad', 'entry_level', 'mid_level', 'senior', 'staff', 'senior_staff', 'principal', 'manager', 'multiple_levels')", name='ck_jpa_seniority'),
    sa.CheckConstraint('(cardinality(other_relevant_information) = 0 OR array_ndims(other_relevant_information) = 1) AND array_position(other_relevant_information, NULL) IS NULL', name='ck_jpa_other_information_array'),
    sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_posting_id')
    )
    op.create_index('ix_jpa_family_seniority', 'job_postings_analyses', ['job_family', 'seniority'], unique=False)
    op.create_table('job_analysis_locations',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_posting_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("CASE WHEN jsonb_typeof(evidence) = 'array' THEN jsonb_array_length(evidence) > 0 ELSE false END", name='ck_jal_evidence'),
    sa.CheckConstraint("btrim(value) <> ''", name='ck_jal_value'),
    sa.CheckConstraint('position >= 0', name='ck_jal_position'),
    sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings_analyses.job_posting_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_posting_id', 'position', name='uq_jal_position')
    )
    op.create_table('job_analysis_responsibilities',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_posting_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("CASE WHEN jsonb_typeof(evidence) = 'array' THEN jsonb_array_length(evidence) > 0 ELSE false END", name='ck_jar_evidence'),
    sa.CheckConstraint("btrim(value) <> ''", name='ck_jar_value'),
    sa.CheckConstraint('position >= 0', name='ck_jar_position'),
    sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings_analyses.job_posting_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_posting_id', 'position', name='uq_jar_position')
    )
    op.create_table('job_analysis_qualifications',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_posting_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('level', sa.Text(), nullable=False),
    sa.Column('categories', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("CASE WHEN jsonb_typeof(evidence) = 'array' THEN jsonb_array_length(evidence) > 0 ELSE false END", name='ck_jaq_evidence'),
    sa.CheckConstraint("array_ndims(categories) = 1 AND cardinality(categories) > 0 AND array_position(categories, NULL) IS NULL AND categories <@ ARRAY['skill', 'experience', 'education', 'certification', 'domain_knowledge', 'language', 'competency', 'other']::text[]", name='ck_jaq_categories'),
    sa.CheckConstraint("btrim(value) <> ''", name='ck_jaq_value'),
    sa.CheckConstraint("level IN ('required', 'preferred', 'unspecified')", name='ck_jaq_level'),
    sa.CheckConstraint('position >= 0', name='ck_jaq_position'),
    sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings_analyses.job_posting_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_posting_id', 'position', name='uq_jaq_position')
    )
    op.create_table('job_analysis_conditions',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_posting_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("CASE WHEN jsonb_typeof(evidence) = 'array' THEN jsonb_array_length(evidence) > 0 ELSE false END", name='ck_jac_evidence'),
    sa.CheckConstraint("btrim(value) <> ''", name='ck_jac_value'),
    sa.CheckConstraint("type IN ('employment_type', 'workplace_arrangement', 'geographic_restriction', 'schedule', 'travel', 'visa_sponsorship', 'work_authorization', 'citizenship_requirement', 'security_clearance', 'export_control', 'other')", name='ck_jac_type'),
    sa.CheckConstraint('position >= 0', name='ck_jac_position'),
    sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings_analyses.job_posting_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_posting_id', 'position', name='uq_jac_position')
    )
    op.create_table('job_analysis_compensation',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_posting_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('minimum', sa.Numeric(), nullable=True),
    sa.Column('maximum', sa.Numeric(), nullable=True),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('interval', sa.Text(), nullable=True),
    sa.Column('applies_to', sa.Text(), nullable=True),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("CASE WHEN jsonb_typeof(evidence) = 'array' THEN jsonb_array_length(evidence) > 0 ELSE false END", name='ck_jap_evidence'),
    sa.CheckConstraint("btrim(applies_to) <> ''", name='ck_jap_applies_to'),
    sa.CheckConstraint("btrim(currency) <> ''", name='ck_jap_currency'),
    sa.CheckConstraint("btrim(value) <> ''", name='ck_jap_value'),
    sa.CheckConstraint("interval IN ('hour', 'day', 'week', 'month', 'year', 'one_time')", name='ck_jap_interval'),
    sa.CheckConstraint("maximum >= 0 AND maximum NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_jap_maximum'),
    sa.CheckConstraint("minimum >= 0 AND minimum NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_jap_minimum'),
    sa.CheckConstraint("type IN ('base_salary', 'hourly_rate', 'ote', 'bonus', 'commission', 'equity', 'stipend', 'other')", name='ck_jap_type'),
    sa.CheckConstraint('minimum <= maximum', name='ck_jap_bounds'),
    sa.CheckConstraint('position >= 0', name='ck_jap_position'),
    sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings_analyses.job_posting_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_posting_id', 'position', name='uq_jap_position')
    )
    op.execute('ALTER TABLE job_postings_analyses ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE job_analysis_locations ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE job_analysis_responsibilities ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE job_analysis_qualifications ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE job_analysis_conditions ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE job_analysis_compensation ENABLE ROW LEVEL SECURITY')



def downgrade() -> None:
    op.drop_table('job_analysis_compensation')
    op.drop_table('job_analysis_conditions')
    op.drop_table('job_analysis_qualifications')
    op.drop_table('job_analysis_responsibilities')
    op.drop_table('job_analysis_locations')
    op.drop_index('ix_jpa_family_seniority', table_name='job_postings_analyses')
    op.drop_table('job_postings_analyses')

