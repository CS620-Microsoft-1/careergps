"""Create student_courses: school courses a student has taken.

Revision ID: 9aa1698efdd2
Revises: e93b20128bb7

One row per student and course, not per role: a course taken counts for every destination.
course_id references school_courses, whose rows are never deleted (only set inactive), so
ON DELETE RESTRICT never blocks normal use. source records how the row was added: the Taken
button ('manual'), a confirmed résumé match ('resume') or a plan item marked done ('plan').
Schema only: no data copy. RLS follows the backend-only access model (Supabase Data API
disabled); no anonymous/authenticated policies. The database owner applies this after merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "9aa1698efdd2"
down_revision = "e93b20128bb7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('student_courses',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('course_id', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), server_default=sa.text("'manual'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('manual', 'resume', 'plan')", name='ck_student_courses_source'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['school_courses.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('user_id', 'course_id')
    )
    op.create_index('ix_student_courses_course_id', 'student_courses', ['course_id'], unique=False)

    # Added by hand (autogenerate doesn't know about RLS); see the users migration.
    op.execute("ALTER TABLE student_courses ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index('ix_student_courses_course_id', table_name='student_courses')
    op.drop_table('student_courses')
