from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# pool_pre_ping checks a connection is still alive before using it,
# which avoids errors after the Supabase pooler closes idle connections.
# The transaction pooler can hand each transaction a different server connection, so psycopg must
# not create prepared statements (prepare_threshold=None).
# connect_timeout (seconds) makes an unreachable database fail fast instead of hanging requests, including
# the agent_calls row written after every Agent call.
CONNECT_TIMEOUT_SECONDS = 5

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None, "connect_timeout": CONNECT_TIMEOUT_SECONDS},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
