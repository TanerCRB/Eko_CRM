"""Alembic environment: run only by the `migrate` service (ADR-0004 *Migrations*).

An upgrade is one connection and one transaction, in the order the ADR-0004 addendum of
2026-10-29 fixes: the advisory lock (no time limit), then the lock and statement timeouts, then the
revision read and descent check, then the pending revisions, then the lineage record. Commit or
rollback releases the lock.
"""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.settings import MigrateSettings, Settings, load_settings
from app.data import models
from app.data.database import connect_args, database_url
from app.data.schema_revision import (
    RevisionRefused,
    check_migratable,
    code_tree,
    read_database_revision,
    set_migration_timeouts,
    take_migration_lock,
    write_lineage,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")
target_metadata = models.Base.metadata


def destination() -> str | None:
    """The command's destination in the code's own tree; None for a command without one."""
    try:
        target = context.get_revision_argument()
    except KeyError:
        # `alembic check` and `current` pass no destination revision: they change nothing.
        return None
    return target if isinstance(target, str) else None


def run_upgrade() -> None:
    settings = load_settings(MigrateSettings)
    tree = code_tree()
    if destination() != tree.head:
        raise SystemExit(f"migrate refused: it upgrades only to the code's head ({tree.head})")
    # NullPool: one migration run holds one connection (ADR-0003-C19 counts exactly one).
    engine = create_engine(
        database_url(settings), poolclass=pool.NullPool, connect_args=connect_args(settings)
    )
    try:
        with engine.connect() as connection, connection.begin():
            take_migration_lock(connection, settings.migration_advisory_lock_key)
            set_migration_timeouts(
                connection,
                settings.migration_lock_timeout_seconds,
                settings.migration_statement_timeout_seconds,
            )
            try:
                pending = check_migratable(read_database_revision(connection), tree)
            except RevisionRefused as refused:
                raise SystemExit(f"migrate refused: {refused}") from None
            if not pending:
                logger.info("migrate: nothing to apply")
                return
            # Inside the outer transaction Alembic opens none of its own and commits nothing.
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
            write_lineage(connection, tree)
    finally:
        engine.dispose()


def run_read_only() -> None:
    settings = load_settings(Settings)
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
if destination() is None:
    run_read_only()
else:
    run_upgrade()
