import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Profile(Base):
    """Career goal and background for one user (1:1 with users)."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Allowed values are checked by the API (app/core/options.py), not by a DB enum,
    # so the list can change without a migration.
    target_role: Mapped[str] = mapped_column(String(100), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(50), nullable=False)
    graduation_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    university: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str | None] = mapped_column(String(100))
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Profile {self.user_id}>"
