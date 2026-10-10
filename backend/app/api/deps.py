from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Iterator[Session]:
    """Give each request its own session and always close it, returning the connection to the pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
