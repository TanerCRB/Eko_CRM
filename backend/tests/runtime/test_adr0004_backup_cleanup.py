"""K-05, K-07 and G-8 A (fix round 1, S-01 = F-02 = R-01): every failed run, including an
interrupted one and one whose control session fails, ends with exactly one line, the documented
failure line, and leaves nothing behind: no ssh-agent holding the destination credential, no
tool, and no run directory under /tmp.

The runs are started with `docker compose exec` in the long-running scheduler container, the
place where a leftover would accumulate night after night. Their whole output is checked, not
only the lines that match the failure pattern.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.runtime.backup_lab import (
    RUN_DIRS,
    BackupLab,
    ExecRun,
    RunResult,
    failure_fields,
    failure_lines,
    run_leftovers,
)
from tests.runtime.test_adr0004_backup_failure_line import backup_lines

pytestmark = pytest.mark.runtime

PLANTED = RUN_DIRS + "planted"


@pytest.fixture
def scheduler(backup_lab: BackupLab) -> Iterator[str]:
    container = backup_lab.scheduler()
    assert run_leftovers(container) == [], "the scheduler container is not clean to begin with"
    try:
        yield container
    finally:
        backup_lab.stop_scheduler()


def the_one_line(result: RunResult) -> dict[str, str]:
    assert result.code != 0
    lines = backup_lines(result.output)
    assert len(lines) == 1, lines
    assert failure_lines(lines[0]) == lines, lines
    return failure_fields(lines[0])


def lose_control_at_h1(backup_lab: BackupLab) -> None:
    with backup_lab.keycloak_table_held():
        backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
        backup_lab.sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE application_name = 'eko-backup-control'"
        )


@contextmanager
def revision_denied(backup_lab: BackupLab) -> Iterator[None]:
    """The control session's revision query refused (42501), as a forgotten grant would."""
    backup_lab.sql("REVOKE SELECT ON alembic_version FROM eko_backup")
    try:
        yield
    finally:
        backup_lab.sql("GRANT SELECT ON alembic_version TO eko_backup")


def test_g8_an_interrupted_run_in_the_scheduler_writes_one_line_and_leaves_nothing(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.at_probe_head()
    with backup_lab.keycloak_table_held():
        run = ExecRun(backup_lab.composition)
        backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
        backup_lab.interrupt_exec_run(scheduler)
        result = run.wait()
    assert the_one_line(result)["reason"] == "interrupted"
    backup_lab.wait_until("the sessions end", lambda: backup_lab.backup_sessions() == [])
    assert run_leftovers(scheduler) == []


def test_r01_the_control_session_lost_at_h1_writes_one_line_and_leaves_nothing(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.at_probe_head()
    run = ExecRun(backup_lab.composition)
    lose_control_at_h1(backup_lab)
    fields = the_one_line(run.wait())
    assert (fields["reason"], fields.get("sqlstate")) == ("lock", "57P01"), fields
    assert run_leftovers(scheduler) == []


def test_r01_a_refusal_on_the_control_session_writes_one_line_and_leaves_nothing(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.at_probe_head()
    with revision_denied(backup_lab):
        result = ExecRun(backup_lab.composition).wait()
    fields = the_one_line(result)
    assert (fields["reason"], fields.get("sqlstate")) == ("dump-application", "42501"), fields
    assert run_leftovers(scheduler) == []


def test_r01_a_control_session_refused_at_connect_writes_one_line_and_leaves_nothing(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.at_probe_head()
    wrong = dict([("BACKUP_DB_PASSWORD", "synthetic-wrong")])
    result = ExecRun(backup_lab.composition, env=wrong).wait()
    fields = the_one_line(result)
    assert (fields["reason"], fields.get("sqlstate")) == ("database", "28P01"), fields
    assert run_leftovers(scheduler) == []


# QA (fix round 1): every failure above happens after the ssh-agent has started, so the agent's
# variables are always set by the time the cleanup runs. A run refused before the agent starts
# (a host-key line ssh-keygen cannot fingerprint) is the one exit path where the cleanup reads a
# variable the run never set: the contrast to the 28P01 run, with only the failure point moved.


def test_r01_a_run_refused_before_the_agent_starts_writes_one_line_and_leaves_nothing(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.at_probe_head()
    unreadable = dict([("BACKUP_DESTINATION_HOST_KEY", "ssh-ed25519 AAAAsynthetic-not-a-key")])
    result = ExecRun(backup_lab.composition, env=unreadable).wait()
    fields = the_one_line(result)
    assert fields["reason"] == "destination", fields
    assert "sqlstate" not in fields, fields
    assert run_leftovers(scheduler) == []


def test_r01_contrast_a_successful_run_in_the_scheduler_leaves_nothing(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.at_probe_head()
    result = ExecRun(backup_lab.composition).wait()
    assert result.code == 0, result.stderr
    [line] = backup_lines(result.output)
    assert line.startswith("eko-backup: run succeeded ")
    assert run_leftovers(scheduler) == []


def test_r01_contrast_the_leftover_check_sees_an_agent_and_a_run_directory(
    backup_lab: BackupLab, scheduler: str
) -> None:
    backup_lab.composition.compose(
        "exec", "-T", "-d", "backup", "sh", "-c",
        f"mkdir -p {PLANTED} && exec ssh-agent -D -a {PLANTED}/agent",
    )  # fmt: skip
    backup_lab.wait_until("the planted agent runs", lambda: len(run_leftovers(scheduler)) >= 2)
    left = run_leftovers(scheduler)
    assert any("ssh-agent" in item for item in left), left
    assert PLANTED in left, left
