"""K-07 (ADR-0004-C28, addendum 2026-10-28 and 2026-10-30): eko_backup reads, never writes. It is
no superuser and creates neither roles nor databases; an insert, an update, a delete and a DDL
statement on either database are each refused with SQLSTATE 42501.

Contrast: a SELECT by eko_backup on the same tables succeeds, so 42501 is a privilege refusal and
not a failed connection.
"""

import re

import pytest

from tests.runtime.backup_lab import BackupLab

pytestmark = pytest.mark.runtime

WRITES = {
    "eko": [
        "INSERT INTO alembic_version (version_num) VALUES ('eko_test')",
        "UPDATE alembic_version SET version_num = version_num",
        "DELETE FROM alembic_version",
        "CREATE TABLE public.eko_test_backup_write (id integer)",
    ],
    "keycloak": [
        "INSERT INTO realm (id) VALUES ('eko-test')",
        "UPDATE realm SET name = name",
        "DELETE FROM realm",
        "CREATE TABLE public.eko_test_backup_write (id integer)",
    ],
}
READS = {"eko": "SELECT count(*) FROM alembic_version", "keycloak": "SELECT count(*) FROM realm"}


def sqlstates(backup_lab: BackupLab, database: str, statement: str) -> list[str]:
    """The SQLSTATE of each error the statement raises as eko_backup, from one psql process at
    verbose error verbosity, read after it has exited (no interleaving of its two streams)."""
    result = backup_lab.composition.compose(
        "exec", "-T", "postgres", "psql", "-X", "-U", "eko_backup", "-d", database,
        "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-c", statement,
        check=False,
    )  # fmt: skip
    return re.findall(r"^(?:ERROR|FATAL):\s+([0-9A-Z]{5}):", result.stderr, re.MULTILINE)


def test_k07_eko_backup_has_no_superuser_createrole_or_createdb(backup_lab: BackupLab) -> None:
    [row] = backup_lab.sql(
        "SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = 'eko_backup'"
    )
    assert row == ["f", "f", "f"]


@pytest.mark.parametrize(
    ("database", "statement"),
    [(database, statement) for database, statements in WRITES.items() for statement in statements],
)
def test_k07_every_write_by_eko_backup_is_refused_with_42501(
    backup_lab: BackupLab, database: str, statement: str
) -> None:
    backup_lab.at_probe_head()
    assert sqlstates(backup_lab, database, statement) == ["42501"]


@pytest.mark.parametrize("database", sorted(READS))
def test_k07_contrast_a_select_by_eko_backup_succeeds(backup_lab: BackupLab, database: str) -> None:
    backup_lab.at_probe_head()
    assert sqlstates(backup_lab, database, READS[database]) == []
