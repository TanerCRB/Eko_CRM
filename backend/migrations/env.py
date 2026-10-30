"""Alembic environment: run only by the `migrate` service (ADR-0004 *Migrations*).

An upgrade is one connection and one transaction, in the order the ADR-0004 addendum of
2026-10-29 fixes: the advisory lock (no time limit), then the lock and statement timeouts, then the
revision read and descent check, then the pending revisions, then the lineage record. Commit or
rollback releases the lock.

Only `alembic upgrade head` changes anything. A command is dispatched on whether it carries a
destination at all, never on the value Alembic resolves it to (`heads` resolves to a tuple, `base`
to None): any destination but the code's head is refused before connecting, and a step that is not
an upgrade (a stamp, a downgrade) is refused inside the run's transaction, which rolls it back. A
command with no destination (`check`, `current`) runs in a read-only transaction.
"""

import logging
from collections.abc import Collection, Mapping
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.runtime.migration import MigrationContext, MigrationInfo
from alembic.util import CommandError
from sqlalchemy import create_engine, pool, text

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


class NoDestination:
    """The command carries no destination revision (`check`, `current`)."""


def destination() -> object:
    """The command's destination as Alembic resolves it, or NoDestination when it has none."""
    try:
        return context.get_revision_argument()
    except KeyError:
        return NoDestination
    except CommandError:
        # An identifier the code's tree cannot resolve.
        raise SystemExit("migrate refused: unknown destination revision") from None


def refuse_unless_upgrade(
    ctx: MigrationContext, step: MigrationInfo, heads: Collection[Any], run_args: Mapping[str, Any]
) -> None:
    """Called by Alembic after each step, still inside the run's one transaction."""
    if step.is_stamp or not step.is_upgrade:
        raise SystemExit("migrate refused: it only upgrades; a stamp or downgrade is not run")


def refuse_any_step(
    ctx: MigrationContext, step: MigrationInfo, heads: Collection[Any], run_args: Mapping[str, Any]
) -> None:
    raise SystemExit("migrate refused: a command without a destination applies nothing")


def run_upgrade() -> None:
    tree = code_tree()
    target = destination()
    if not isinstance(target, str) or target != tree.head:
        raise SystemExit(f"migrate refused: it upgrades only to the code's head ({tree.head})")
    settings = load_settings(MigrateSettings)
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
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                on_version_apply=refuse_unless_upgrade,
            )
            with context.begin_transaction():
                context.run_migrations()
            write_lineage(connection, tree)
    finally:
        engine.dispose()


def run_without_destination() -> None:
    """`alembic check` or `current`: reads only, in a transaction the server keeps read-only."""
    settings = load_settings(Settings)
    engine = create_engine(
        database_url(settings), poolclass=pool.NullPool, connect_args=connect_args(settings)
    )
    try:
        with engine.connect() as connection, connection.begin() as transaction:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                on_version_apply=refuse_any_step,
            )
            with context.begin_transaction():
                context.run_migrations()
            transaction.rollback()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not used: migrate runs against the database")
if destination() is NoDestination:
    run_without_destination()
else:
    run_upgrade()
