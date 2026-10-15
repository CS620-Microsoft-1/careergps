from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401  (registers all models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read the URL from settings (.env) rather than alembic.ini so credentials are never committed.
DATABASE_URL = get_settings().database_url

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate away from Supabase's auth schema.

    users.id -> auth.users.id is added by hand in a migration; without this filter, autogenerate
    would see it in the database but not in the models and propose dropping it.
    """
    if type_ == "foreign_key_constraint" and obj.referred_table.schema == "auth":
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
