"""The schema revision check shared by backend, worker and migrate (ADR-0004 addendum 2026-10-29).

A revision the running code does not ship is placed from `schema_revision_lineage`, which only
migrate writes, in the transaction that moves `alembic_version`. The code's own tree is read from
the revision files' source, never by importing Alembic: application code does not depend on the
migration tool (ADR-0004 *Migrations*).
"""

import ast
import enum
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, create_engine, pool, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import Settings
from app.data.database import connect_args, database_url

logger = logging.getLogger(__name__)

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"


class RevisionRefused(Exception):
    """The database's revision is one this code may not serve, work or migrate on."""


@dataclass(frozen=True)
class RevisionTree:
    """The code's revisions from the base to its single head, in order."""

    revisions: tuple[str, ...]

    @property
    def head(self) -> str:
        return self.revisions[-1]


@dataclass(frozen=True)
class DatabaseRevision:
    """`alembic_version` rows (None: no table) and lineage rows (None: no table)."""

    versions: tuple[str, ...] | None
    lineage: frozenset[str] | None


class Placement(enum.Enum):
    EMPTY = "no alembic_version table"
    NO_ROW = "alembic_version holds no row"
    SEVERAL_ROWS = "alembic_version holds more than one row"
    HEAD = "the code's head"
    ANCESTOR = "older than the code's head"
    DESCENDANT = "a recorded descendant of the code's head"
    UNPLACEABLE = "not placeable from the code's head"


def _revision_assignments(source: str) -> dict[str, object]:
    found: dict[str, object] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target, value = node.targets[0].id, node.value
        else:
            continue
        if target in {"revision", "down_revision"} and isinstance(value, ast.Constant):
            found[target] = value.value
    return found


def tree_from_files(versions_dir: Path) -> RevisionTree:
    """The linear tree of the revision files in a directory; anything else is refused."""
    parents: dict[str, str | None] = {}
    for path in sorted(versions_dir.glob("*.py")):
        # The files Alembic skips: package markers and editor lock files.
        if path.name.startswith(("__init__", ".#")):
            continue
        found = _revision_assignments(path.read_text(encoding="utf-8"))
        revision, parent = found.get("revision"), found.get("down_revision")
        if not isinstance(revision, str) or not (parent is None or isinstance(parent, str)):
            raise RevisionRefused(f"{path.name}: no single revision and parent")
        if revision in parents:
            raise RevisionRefused(f"revision {revision} defined twice")
        parents[revision] = parent
    heads = set(parents) - {p for p in parents.values() if p is not None}
    if len(heads) != 1:
        raise RevisionRefused(f"the code's tree has {len(heads)} heads: {sorted(heads)}")
    chain: list[str] = []
    current: str | None = heads.pop()
    while current is not None:
        if current not in parents or current in chain:
            raise RevisionRefused(f"the code's tree is broken at {current}")
        chain.append(current)
        current = parents[current]
    if len(chain) != len(parents):
        raise RevisionRefused("the code's tree is not linear")
    return RevisionTree(tuple(reversed(chain)))


def code_tree() -> RevisionTree:
    """The tree of the image's own `migrations/versions/`."""
    return tree_from_files(VERSIONS_DIR)


def place(database: DatabaseRevision, tree: RevisionTree) -> Placement:
    if database.versions is None:
        return Placement.EMPTY
    if not database.versions:
        return Placement.NO_ROW
    if len(database.versions) > 1:
        return Placement.SEVERAL_ROWS
    [revision] = database.versions
    if revision == tree.head:
        return Placement.HEAD
    if revision in tree.revisions:
        return Placement.ANCESTOR
    lineage = database.lineage or frozenset()
    if revision in lineage and tree.head in lineage:
        return Placement.DESCENDANT
    return Placement.UNPLACEABLE


def _reason(placement: Placement, database: DatabaseRevision, tree: RevisionTree) -> str:
    found = ", ".join(database.versions or ()) or "none"
    return f"database revision {found} is {placement.value} ({tree.head})"


def check_servable(database: DatabaseRevision, tree: RevisionTree) -> None:
    """backend and worker: only the code's head and a recorded descendant are served."""
    placement = place(database, tree)
    if placement not in {Placement.HEAD, Placement.DESCENDANT}:
        raise RevisionRefused(_reason(placement, database, tree))


def check_migratable(database: DatabaseRevision, tree: RevisionTree) -> bool:
    """migrate: True when there is something to apply, False for a no-op run, else refused."""
    placement = place(database, tree)
    if placement in {Placement.EMPTY, Placement.ANCESTOR}:
        return True
    if placement in {Placement.HEAD, Placement.DESCENDANT}:
        return False
    raise RevisionRefused(_reason(placement, database, tree))


def read_database_revision(connection: Connection) -> DatabaseRevision:
    # Unqualified, so the tables are found on the search path as Alembic finds alembic_version.
    has_versions, has_lineage = connection.execute(
        text(
            "SELECT to_regclass('alembic_version') IS NOT NULL, "
            "to_regclass('schema_revision_lineage') IS NOT NULL"
        )
    ).one()
    versions = None
    if has_versions:
        rows = connection.execute(text("SELECT version_num FROM alembic_version"))
        versions = tuple(sorted(row[0] for row in rows))
    lineage = None
    if has_lineage:
        rows = connection.execute(text("SELECT revision FROM schema_revision_lineage"))
        lineage = frozenset(row[0] for row in rows)
    return DatabaseRevision(versions, lineage)


def take_migration_lock(connection: Connection, key: int) -> None:
    """The run's advisory lock, transaction-level, single-bigint form; waits with no limit."""
    connection.execute(text("SELECT pg_advisory_xact_lock(CAST(:key AS bigint))"), {"key": key})


def set_migration_timeouts(
    connection: Connection, lock_timeout_seconds: int, statement_timeout_seconds: int
) -> None:
    """Both timeouts for the rest of the current transaction only (`is_local` true)."""
    connection.execute(
        text(
            "SELECT set_config('lock_timeout', :lock, true), "
            "set_config('statement_timeout', :statement, true)"
        ),
        {"lock": f"{lock_timeout_seconds}s", "statement": f"{statement_timeout_seconds}s"},
    )


def write_lineage(connection: Connection, tree: RevisionTree) -> None:
    """Replace the record with the lineage of the code's head, in the caller's transaction."""
    connection.execute(text("DELETE FROM schema_revision_lineage"))
    connection.execute(
        text("INSERT INTO schema_revision_lineage (revision) VALUES (:revision)"),
        [{"revision": revision} for revision in tree.revisions],
    )


def refuse_unless_servable(settings: Settings, process: str) -> None:
    """Stop the process unless the database is at the code's head or a recorded descendant.

    One connection of its own, closed before returning; never the advisory lock.
    """
    engine = create_engine(
        database_url(settings), poolclass=pool.NullPool, connect_args=connect_args(settings)
    )
    try:
        with engine.connect() as connection:
            database = read_database_revision(connection)
        check_servable(database, code_tree())
    except SQLAlchemyError as exc:
        # Type and location only under the process's line form (ADR-0005 addendum 2026-11-02).
        logger.error("the database revision could not be read", exc_info=True)
        # The type only: driver messages name hosts and roles.
        raise SystemExit(
            f"{process} refused to start: the database revision could not be read "
            f"({type(exc).__name__})"
        ) from None
    except RevisionRefused as refused:
        raise SystemExit(f"{process} refused to start: {refused}") from None
    finally:
        engine.dispose()
    logger.info("%s: database revision accepted", process)
