"""K-05, failure line: every failed run exits non-zero with exactly one line of the form
documented in backup/README.md, naming the failure; a successful run writes no such line.

The pattern is read from backup/README.md, the one place it is documented, so the document and
this test cannot drift (ADR-0004 addendum 2026-10-30, *A failed run is one line*).
"""

import re
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


# QA (EKO-1-14): "exactly one line" over the run's whole output, not only over its eko-backup
# lines. A tool's own message (age, pg_dump, bash) is a second line of the log, and ADR-0004's
# addendum forbids it ("no tool's message"); only docker compose's own progress lines are not
# backup's. The successful run likewise writes its one line and nothing else.

COMPOSE_PROGRESS = re.compile(
    r"^ ?Container \S+ (Creating|Created|Starting|Started|Removing|Removed) ?$"
)


def backup_lines(output: str) -> list[str]:
    lines = [line for line in output.splitlines() if line.strip()]
    return [line for line in lines if not COMPOSE_PROGRESS.fullmatch(line)]


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_k05_a_failed_runs_whole_output_is_the_one_line(
    backup_lab: BackupLab, failure: str
) -> None:
    backup_lab.at_probe_head()
    prepare, env, reason = FAILURES[failure]
    with prepare(backup_lab):
        result = backup_lab.run(env=env)
    assert result.code != 0
    [line] = backup_lines(result.output)
    assert failure_lines(line) == [line]
    assert failure_fields(line)["reason"] == reason, line


def test_k05_contrast_a_successful_runs_whole_output_is_the_success_line(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    [line] = backup_lines(result.output)
    assert line.startswith("eko-backup: run succeeded ")


def test_k05_contrast_the_line_filter_keeps_a_tools_message() -> None:
    output = " Container bkp-1 Creating \n Container bkp-1 Created \nage: error: bad key\nx\n"
    assert backup_lines(output) == ["age: error: bad key", "x"]


def test_k05_a_wrong_host_key_fails_before_anything_reaches_the_destination(
    backup_lab: BackupLab,
) -> None:
    """QA (EKO-1-14): backup checks the destination's host key and never accepts another one
    (ADR-0004 addendum 2026-10-30, *The destination's identity*). With a different valid key
    configured, the run fails with reason=destination and the double records no request from
    backup's credential: no object is sent to a host that was not verified."""
    backup_lab.at_probe_head()
    double = backup_lab.double
    other = double.sh(
        "f=/tmp/qa-other-host-key; rm -f $f $f.pub; ssh-keygen -q -t ed25519 -N '' -f $f "
        "&& cat $f.pub"
    ).strip()
    assert other.startswith("ssh-ed25519 ") and other.split()[1] not in double.host_key
    since = len(double.records())
    result = backup_lab.run(env=dict([("BACKUP_DESTINATION_HOST_KEY", other)]))
    assert result.code != 0
    [line] = failure_lines(result.output)
    assert failure_fields(line)["reason"] == "destination", line
    assert [r for r in double.records()[since:] if r["credential"] == "eko-backup"] == []


def test_k05_contrast_the_configured_host_key_lets_the_run_reach_the_destination(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    double = backup_lab.double
    since = len(double.records())
    result = backup_lab.run(env=dict([("BACKUP_DESTINATION_HOST_KEY", double.host_key)]))
    assert result.code == 0, result.stderr
    assert [r for r in double.records()[since:] if r["credential"] == "eko-backup"] != []
