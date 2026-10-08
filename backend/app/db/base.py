from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Parent class for all SQLAlchemy models. Alembic reads Base.metadata to detect schema changes."""
