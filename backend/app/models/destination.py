import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Destination(Base):
    """One target role a student is working toward, and the résumé it is matched against.

    One row per (user, role). Several roles may use the same résumé. users.target_role selects
    the destination the app shows.
    """

    __tablename__ = "destinations"
    __table_args__ = (
        CheckConstraint(
            "job_family IN ('software_engineer', 'data_analyst', 'ai_engineer')", name="ck_destinations_job_family"
        ),
        # The résumé must belong to the same user. A résumé a role uses can't be deleted.
        ForeignKeyConstraint(
            ["resume_id", "user_id"], ["resumes.id", "resumes.user_id"], name="fk_destinations_resume"
        ),
        Index("ix_destinations_resume_id", "resume_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    job_family: Mapped[str] = mapped_column(Text, primary_key=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Destination {self.user_id} {self.job_family} -> {self.resume_id}>"
