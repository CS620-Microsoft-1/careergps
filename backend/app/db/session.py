from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# pool_pre_ping checks a connection is still alive before using it,
# which avoids errors after the Supabase pooler closes idle connections.
# The transaction pooler can hand each transaction a different server connection, so psycopg must
# not create prepared statements (prepare_threshold=None).
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
