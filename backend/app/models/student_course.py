"""School courses a student has taken. One row per student and course, for every role."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SOURCES = ("manual", "resume", "plan")


class StudentCourse(Base):
    __tablename__ = "student_courses"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'resume', 'plan')", name="ck_student_courses_source"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", name="fk_student_courses_user", ondelete="CASCADE"), primary_key=True
    )
    # Catalog rows are never deleted, only set inactive.
    course_id: Mapped[str] = mapped_column(
        Text, ForeignKey("school_courses.id", name="fk_student_courses_course", ondelete="RESTRICT"),
        primary_key=True, index=True
    )
    # How it was added: the Taken button, a confirmed résumé match, or a plan item marked done.
    source: Mapped[str] = mapped_column(Text, server_default=text("'manual'"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
