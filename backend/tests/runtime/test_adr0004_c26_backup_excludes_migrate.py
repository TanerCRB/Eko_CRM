"""K-02 (ADR-0004-C26, backup half): backup and migrate exclude each other on the one advisory lock,
which backup holds from before the application snapshot until the Keycloak dump has ended.

(a) holds backup at H1, inside the Keycloak dump after the application dump: no session of the
application database is held, so a migrate that waits there waits on the advisory lock only.
Its revision creates a new table, which no lock of a dump or of the ended snapshot covers.
(b) holds the lock with a test session at H0 (no table lock).
"""

import time

import pytest

from tests.runtime.backup_lab import (
    KEY,
    LATER_VARIANT,
    BackupLab,
    complete_sets,
    failure_fields,
    failure_lines,
    open_set,
    set_names,
    unique_marker,
)
from tests.support import migration_checks as mc

pytestmark = pytest.mark.runtime

HOLD_SECONDS = 10
LOCK_TWO_INTEGERS = "SELECT pg_advisory_lock(CAST(:'hi' AS integer), CAST(:'lo' AS integer))"
LOCK_OTHER = "SELECT pg_advisory_lock(CAST(:'k' AS bigint))"


def test_k02_a_migrate_applies_no_ddl_while_backup_is_in_the_keycloak_dump(
    backup_lab: BackupLab,
) -> None:
    lab = backup_lab.lab
    backup_lab.at_probe_head()
    before = lab.comparison_dump()
    variant = lab.variant("backup_later", LATER_VARIANT)
    before_sets = set_names(backup_lab.double)
    migrate = None
    try:
        with backup_lab.keycloak_table_held():
            run = backup_lab.start_run()
            backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
            assert not [
                s
                for s in backup_lab.backup_sessions()
                if s[0] == "eko" and s[1] != "eko-backup-control"
            ]
            migrate = lab.start_migrate(variant)
            held = time.monotonic()
            while time.monotonic() < held + HOLD_SECONDS:
                assert migrate.running(), migrate.logs()
                assert lab.comparison_dump() == before
                time.sleep(2)
            assert run.running()
        result = run.wait()
        assert result.code == 0, result.stderr
        assert migrate.wait(120) == 0, migrate.logs()
    finally:
        if migrate is not None:
            migrate.remove()
    assert lab.versions() == ["t_backup_later"]
    assert (set_names(backup_lab.double) - before_sets) <= complete_sets(backup_lab.double)


def test_k02_a_contrast_with_no_backup_the_same_revision_applies_at_once(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    started = time.monotonic()
    code, logs = backup_lab.lab.run_migrate(backup_lab.lab.variant("backup_later", LATER_VARIANT))
    assert code == 0, logs
    assert time.monotonic() - started < 60
    assert backup_lab.lab.versions() == ["t_backup_later"]


def test_k02_a_edge_a_run_failing_while_it_holds_the_lock_releases_it(
    backup_lab: BackupLab,
) -> None:
    lab = backup_lab.lab
    backup_lab.at_probe_head()
    migrate = None
    try:
        with backup_lab.keycloak_table_held():
            run = backup_lab.start_run()
            backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
            migrate = lab.start_migrate(lab.variant("backup_later", LATER_VARIANT))
            time.sleep(3)
            assert migrate.running()
            backup_lab.keycloak_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE application_name = 'eko-backup-dump-keycloak'"
            )
            result = run.wait()
        assert result.code != 0
        [line] = failure_lines(result.stderr)
        assert failure_fields(line)["reason"] == "dump-keycloak", line
        assert migrate.wait(120) == 0, migrate.logs()
    finally:
        if migrate is not None:
            migrate.remove()
    assert lab.versions() == ["t_backup_later"]


def test_k02_b_backup_starts_no_dump_while_the_lock_is_held(backup_lab: BackupLab) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    with backup_lab.advisory_lock_held() as holder:
        run = backup_lab.start_run()
        backup_lab.wait_until(
            "backup waits for the advisory lock",
            lambda: ("eko", "eko-backup-control", "Lock") in backup_lab.backup_sessions(),
        )
        held = time.monotonic()
        while time.monotonic() < held + HOLD_SECONDS:
            sessions = backup_lab.backup_sessions()
            assert backup_lab.dump_sessions() == [], sessions
            assert [s for s in sessions if s[0] == "keycloak"] == [], sessions
            assert run.running()
            time.sleep(0.5)
        holder.query("SELECT pg_advisory_unlock(CAST(:'k' AS bigint))", k=str(KEY))
    result = run.wait()
    assert result.code == 0, result.stderr
    new = set_names(backup_lab.double) - before
    assert len(new) == 1 and new <= complete_sets(backup_lab.double)


@pytest.mark.parametrize("form", ["two-integer", "other-bigint"])
def test_k02_b_contrast_another_lock_does_not_hold_backup(backup_lab: BackupLab, form: str) -> None:
    backup_lab.at_probe_head()
    if form == "two-integer":
        high, low = mc.two_integer_form(KEY)
        statement, keys = LOCK_TWO_INTEGERS, {"hi": str(high), "lo": str(low)}
    else:
        statement, keys = LOCK_OTHER, {"k": str(KEY ^ 1)}
    with backup_lab.advisory_lock_held(statement, **keys):
        run = backup_lab.start_run()
        backup_lab.wait_until(
            "a dump session starts", lambda: bool(backup_lab.dump_sessions()) or not run.running()
        )
        result = run.wait()
    assert result.code == 0, result.stderr


def test_k02_b_the_snapshot_is_taken_after_the_lock_is_granted(backup_lab: BackupLab) -> None:
    """QA (EKO-1-14): the lock is held from *before* the application snapshot. A row committed
    while backup waits at H0 is in the application dump, so the dump's snapshot postdates the
    grant (ADR-0004 addendum 2026-10-30: the lock is never first taken inside the transaction
    whose snapshot the dump uses). Without this, a snapshot fixed before the wait passes (b)."""
    backup_lab.at_probe_head()
    marker = unique_marker("k02-waited")
    before = set_names(backup_lab.double)
    with backup_lab.advisory_lock_held() as holder:
        run = backup_lab.start_run()
        backup_lab.wait_until(
            "backup waits for the advisory lock",
            lambda: ("eko", "eko-backup-control", "Lock") in backup_lab.backup_sessions(),
        )
        backup_lab.plant_row(marker)
        holder.query("SELECT pg_advisory_unlock(CAST(:'k' AS bigint))", k=str(KEY))
    result = run.wait()
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    contents = open_set(backup_lab.double, name, backup_lab.identity)
    assert marker.encode("utf-8") in contents.application
