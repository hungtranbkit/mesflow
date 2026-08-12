from alembic import context
from sqlalchemy import create_engine, pool

from mesflow.core.config import settings

config = context.config
target_metadata = None


def _sqlalchemy_url(database_url: str) -> str:
    """Use SQLAlchemy's psycopg v3 dialect without changing the app DSN."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    raise RuntimeError("Alembic requires a PostgreSQL DATABASE_URL")


SA_DATABASE_URL = _sqlalchemy_url(settings.database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=SA_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        SA_DATABASE_URL,
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
