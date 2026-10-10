from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# pool_pre_ping checks a connection is still alive before using it,
# which avoids errors after the Supabase pooler closes idle connections.
engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
