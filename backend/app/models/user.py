import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """One student. The row is created when onboarding is confirmed, together with the first résumé."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("primary_email = lower(primary_email)", name="ck_users_primary_email_lowercase"),
        CheckConstraint("graduation_year BETWEEN 2000 AND 2100", name="ck_users_graduation_year_range"),
    )

    # Same id as the Supabase Auth account (auth.users.id), never generated here.
    # The foreign key to auth.users lives only in the migration: auth is Supabase's schema, not ours.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # Login email, copied from Supabase Auth and kept in sync on login.
    primary_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # From the confirmed résumé; may be missing or differ from first + last name.
    full_name: Mapped[str | None] = mapped_column(String(255))

    # Career goals from onboarding. target_role is also the selected destination: the agents use
    # the résumé linked to it (resumes.job_family). Allowed roles and levels are validated in the backend, not with a
    # CHECK, so the lists can change without a migration.
    target_role: Mapped[str] = mapped_column(String(30), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    graduation_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    university: Mapped[str] = mapped_column(String(150), nullable=False)
    # Where the student wants to work; filters job postings.
    preferred_location: Mapped[str] = mapped_column(String(100), nullable=False)

    # Contact details from the confirmed résumé. A newer résumé fills only empty fields.
    resume_emails: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'"), nullable=False
    )
    phones: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"), nullable=False)
    # Where the student lives now (from the résumé), unlike preferred_location.
    current_location: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(String(2048))
    github_url: Mapped[str | None] = mapped_column(String(2048))
    website_url: Mapped[str | None] = mapped_column(String(2048))


    # The terms checkbox is on the sign-up page; résumé text is processed by Azure.
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User {self.primary_email}>"
