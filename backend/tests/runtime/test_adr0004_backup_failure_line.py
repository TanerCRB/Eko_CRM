"""K-05, failure line: every failed run exits non-zero with exactly one line of the form
documented in backup/README.md, naming the failure; a successful run writes no such line.

The pattern is read from backup/README.md, the one place it is documented, so the document and
this test cannot drift (ADR-0004 addendum 2026-10-30, *A failed run is one line*).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.runtime.backup_lab import BackupLab, failure_fields, failure_lines

pytestmark = pytest.mark.runtime


@contextmanager
def nothing(_: BackupLab) -> Iterator[None]:
    yield


@contextmanager
def keycloak_connect_revoked(backup_lab: BackupLab) -> Iterator[None]:
    backup_lab.sql("REVOKE CONNECT ON DATABASE keycloak FROM eko_backup")
    try:
        yield
    finally:
        backup_lab.sql("GRANT CONNECT ON DATABASE keycloak TO eko_backup")


FAILURES = {
    "destination-unreachable": (
        nothing,
        {"BACKUP_DESTINATION": "sftp://eko-backup@unreachable.invalid:22/incoming"},
        "destination",
    ),
    "dump-fails": (keycloak_connect_revoked, {}, "dump-keycloak"),
    "encryption-fails": (nothing, dict([("BACKUP_ENCRYPTION_PUBLIC_KEY", "age1x")]), "encryption"),
}


def own_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("eko-backup")]


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_k05_a_failed_run_writes_exactly_one_documented_line(
    backup_lab: BackupLab, failure: str
) -> None:
    backup_lab.at_probe_head()
    prepare, env, reason = FAILURES[failure]
    with prepare(backup_lab):
        result = backup_lab.run(env=env)
    assert result.code != 0
    [line] = failure_lines(result.output)
    assert own_lines(result.output) == [line]
    assert failure_fields(line)["reason"] == reason, line


def test_k05_contrast_a_successful_run_writes_no_failure_line(backup_lab: BackupLab) -> None:
    backup_lab.at_probe_head()
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    assert failure_lines(result.output) == []
    [line] = own_lines(result.output)
    assert line.startswith("eko-backup: run succeeded ")
