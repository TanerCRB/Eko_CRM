"""Alembic environment: run only by the `migrate` service (ADR-0004 *Migrations*)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.settings import Settings, load_settings
from app.data import models
from app.data.database import connect_args, database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.Base.metadata


def run_migrations_online() -> None:
    settings = load_settings(Settings)
    # NullPool: one migration run holds one connection (ADR-0003-C19 counts exactly one).
    engine = create_engine(
        database_url(settings), poolclass=pool.NullPool, connect_args=connect_args(settings)
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not used: migrate runs against the database")
run_migrations_online()
