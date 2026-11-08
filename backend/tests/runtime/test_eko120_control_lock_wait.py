"""EKO-1-20 (ADR-0004 addendum 2026-11-08, ADR-0004-C32): the backup control session's lock
waits after the advisory lock is granted end at the bound; the advisory-lock wait does not.

- K-01: a table lock held before the run on an application table ends the row counts with
  SQLSTATE 55P03 at the bound; nothing reaches the destination, nothing is left behind, and the
  advisory lock is free. Its contrast releases the lock within the bound and the run succeeds.
- K-02: the same on `alembic_version`, so the revision read is bounded too.
- K-03: the advisory lock held past the bound only delays the run; and the bound starts at the
  grant, not at the run's start.
- K-04: no role, database, server setting or `backup` environment carries a lock bound.

Times are on this host's monotonic clock, from the first poll that sees the control session wait
on the held relation. The window is the bound less 5 s for polling, and the bound plus a stated
60 s margin (gate 1 of EKO-1-20); it is not widened when the host is loaded.
"""

import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from tests.runtime.backup_lab import (
    KEY,
    LATER_VARIANT,
    UNLOCK_BIGINT,
    BackupLab,
    BackupRun,
    ExecRun,
    RunResult,
    complete_sets,
    failure_fields,
    failure_lines,
    open_set,
    run_leftovers,
    set_names,
)
from tests.runtime.lab import PsqlSession
from tests.support import migration_checks as mc

pytestmark = pytest.mark.runtime

BOUND_SECONDS = 180.0
EARLIEST = BOUND_SECONDS - 5.0
LATEST = BOUND_SECONDS + 60.0
RELEASE_AFTER = 60.0
MIGRATE_WITHIN = 60.0
ADVISORY_HOLD = 250.0
ADVISORY_FIRST = 120.0
POLL_SECONDS = 0.5
PROBE = "eko_test_backup_probe"
REVISIONS = "alembic_version"
CONTROL = ("eko", "eko-backup-control")
TIMEOUTS = ("lock_timeout", "statement_timeout", "transaction_timeout")
SHOW_TIMEOUTS = "SELECT " + ", ".join(f"current_setting('{name}')" for name in TIMEOUTS)

Run = BackupRun | ExecRun


@pytest.fixture
def scheduler(backup_lab: BackupLab) -> Iterator[str]:
    """The long-running `backup` container, where a run's leftovers stay observable."""
    container = backup_lab.scheduler()
    assert run_leftovers(container) == [], "the scheduler container is not clean to begin with"
    try:
        yield container
    finally:
        backup_lab.stop_scheduler()


@contextmanager
def table_held(backup_lab: BackupLab, table: str) -> Iterator[PsqlSession]:
    holder = PsqlSession(backup_lab.composition, name="eko-test-eko120-holder")
    try:
        holder.query("BEGIN")
        holder.query(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
        yield holder
    finally:
        holder.close()


def control_waits_on(backup_lab: BackupLab, table: str) -> bool:
    [[waiting]] = backup_lab.sql(
        "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
        "WHERE a.application_name = 'eko-backup-control' AND a.wait_event_type = 'Lock' "
        "AND l.locktype = 'relation' AND NOT l.granted "
        "AND l.relation = CAST(:'t' AS regclass)",
        t=table,
    )
    return waiting != "0"


def control_waits_for_the_advisory_lock(backup_lab: BackupLab) -> bool:
    return (*CONTROL, "Lock") in backup_lab.backup_sessions()


def advisory_lock_sessions(backup_lab: BackupLab) -> list[str]:
    """Application names of the sessions holding or waiting for the shared advisory lock."""
    classid, objid, objsubid = mc.pg_locks_identity(KEY)
    rows = backup_lab.sql(
        "SELECT coalesce(a.application_name, '') FROM pg_locks l "
        "LEFT JOIN pg_stat_activity a ON a.pid = l.pid WHERE l.locktype = 'advisory' "
        "AND l.classid = CAST(:'c' AS oid) AND l.objid = CAST(:'o' AS oid) "
        "AND l.objsubid = CAST(:'s' AS smallint)",
        c=str(classid),
        o=str(objid),
        s=str(objsubid),
    )
    return [row[0] for row in rows]


def first_seen(
    backup_lab: BackupLab, condition: str, predicate: Callable[[], bool], timeout: float
) -> float:
    return backup_lab.lab.wait_until(condition, predicate, timeout)


def watch_until_exit(backup_lab: BackupLab, run: Run, deadline: float) -> float:
    """Polls until the run exits or the deadline passes; through the wait the run holds only
    its control session (the two-session budget) and has started no dump. The exit time."""
    while run.running() and time.monotonic() < deadline:
        sessions = backup_lab.backup_sessions()
        assert backup_lab.dump_sessions() == [], sessions
        assert [s[:2] for s in sessions] in ([], [CONTROL]), sessions
        time.sleep(POLL_SECONDS)
    return time.monotonic()


def end_the_run(backup_lab: BackupLab, run: Run) -> None:
    """A run still waiting at its deadline is ended on the server too, or the next test's reset
    waits behind its session (as R-04 ends its run)."""
    backup_lab.sql(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'eko_backup'"
    )
    try:
        run.wait(60)
    except (AssertionError, subprocess.TimeoutExpired):
        pass


def the_bound_failure(result: RunResult) -> None:
    assert result.code != 0
    lines = failure_lines(result.output)
    assert len(lines) == 1, result.output[-3000:]
    fields = failure_fields(lines[0])
    assert (fields["reason"], fields.get("sqlstate")) == ("dump-application", "55P03"), lines[0]


def held_past_the_bound(backup_lab: BackupLab, scheduler: str, table: str) -> None:
    """K-01 and K-02: the run against a table held before it starts and never released."""
    lab = backup_lab.lab
    backup_lab.at_probe_head()
    later = lab.variant("backup_later", LATER_VARIANT)
    before = set_names(backup_lab.double)
    with table_held(backup_lab, table) as holder:
        run = ExecRun(backup_lab.composition)
        try:
            seen = first_seen(
                backup_lab,
                f"the control session waits on {table}",
                lambda: control_waits_on(backup_lab, table),
                120,
            )
            ended = watch_until_exit(backup_lab, run, seen + LATEST)
            assert not run.running(), f"the run still waits {LATEST:g} s after its wait began"
        finally:
            if run.running():
                end_the_run(backup_lab, run)
        result = run.wait(60)
        waited = ended - seen
        assert EARLIEST <= waited <= LATEST, f"the run ended {waited:.1f} s after its wait began"
        the_bound_failure(result)
        assert set_names(backup_lab.double) == before
        assert run_leftovers(scheduler) == []
        assert advisory_lock_sessions(backup_lab) == []
        if table == REVISIONS:
            # A migrate must write alembic_version, so it waits on this lock, not on the
            # advisory one: the advisory lock's release is shown above, its use after the commit.
            holder.query("COMMIT")
        started = time.monotonic()
        code, logs = lab.run_migrate(later, timeout=MIGRATE_WITHIN)
        assert code == 0, logs
        assert time.monotonic() - started < MIGRATE_WITHIN
    assert lab.versions() == ["t_backup_later"]


def released_within_the_bound(
    backup_lab: BackupLab, table: str, with_migrate: bool
) -> tuple[RunResult, dict[str, Any]]:
    """The contrast: the same run, with the table lock committed 60 s after the wait began."""
    lab = backup_lab.lab
    backup_lab.at_probe_head()
    later = lab.variant("backup_later", LATER_VARIANT) if with_migrate else None
    before = set_names(backup_lab.double)
    migrate = None
    try:
        with table_held(backup_lab, table) as holder:
            run = backup_lab.start_run()
            seen = first_seen(
                backup_lab,
                f"the control session waits on {table}",
                lambda: control_waits_on(backup_lab, table),
                120,
            )
            if later is not None:
                migrate = lab.start_migrate(later)
            while time.monotonic() < seen + RELEASE_AFTER:
                assert run.running(), "the run ended before the lock was released"
                assert backup_lab.dump_sessions() == []
                if migrate is not None:
                    assert migrate.running(), migrate.logs()
                time.sleep(POLL_SECONDS)
            holder.query("COMMIT")
            result = run.wait()
        assert result.code == 0, result.stderr
        assert failure_lines(result.output) == []
        new = set_names(backup_lab.double) - before
        assert len(new) == 1 and new <= complete_sets(backup_lab.double), new
        manifest = open_set(backup_lab.double, new.pop(), backup_lab.identity).manifest
        if migrate is not None:
            # Waiting on the advisory lock the run held, it applies once the run has let it go.
            assert migrate.wait(120) == 0, migrate.logs()
            assert lab.versions() == ["t_backup_later"]
    finally:
        if migrate is not None:
            migrate.remove()
    return result, manifest


def test_eko120_k01_counts_held_past_the_bound_fail_with_55p03(
    backup_lab: BackupLab, scheduler: str
) -> None:
    held_past_the_bound(backup_lab, scheduler, PROBE)


def test_eko120_k01_contrast_counts_released_within_the_bound_succeed(
    backup_lab: BackupLab,
) -> None:
    _, manifest = released_within_the_bound(backup_lab, PROBE, with_migrate=True)
    assert f"public.{PROBE}" in manifest["row_counts"], manifest["row_counts"]


def test_eko120_k02_revision_read_held_past_the_bound_fails_with_55p03(
    backup_lab: BackupLab, scheduler: str
) -> None:
    held_past_the_bound(backup_lab, scheduler, REVISIONS)


def test_eko120_k02_contrast_revision_read_released_within_the_bound_succeeds(
    backup_lab: BackupLab,
) -> None:
    _, manifest = released_within_the_bound(backup_lab, REVISIONS, with_migrate=False)
    assert manifest["alembic_revision"] == ",".join(backup_lab.lab.versions() or []), manifest


def test_eko120_k03_an_advisory_lock_held_past_the_bound_only_delays_the_run(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    with backup_lab.advisory_lock_held() as holder:
        run = backup_lab.start_run()
        seen = first_seen(
            backup_lab,
            "the control session waits for the advisory lock",
            lambda: control_waits_for_the_advisory_lock(backup_lab),
            120,
        )
        while time.monotonic() < seen + ADVISORY_HOLD:
            assert run.running(), "the run ended while it waited for the advisory lock"
            sessions = backup_lab.backup_sessions()
            assert [s[:2] for s in sessions] == [CONTROL], sessions
            time.sleep(POLL_SECONDS)
        holder.query(UNLOCK_BIGINT, k=str(KEY))
    result = run.wait()
    assert result.code == 0, result.stderr
    assert failure_lines(result.output) == []
    new = set_names(backup_lab.double) - before
    assert len(new) == 1 and new <= complete_sets(backup_lab.double), new


def test_eko120_k03_edge_the_bound_starts_at_the_grant_not_at_the_run(
    backup_lab: BackupLab,
) -> None:
    """Both locks held before the run; the advisory one released after 120 s. A bound counted
    from the run's start would end it about 60 s after the grant; this one ends it at the bound
    after the grant."""
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    with table_held(backup_lab, PROBE):
        with backup_lab.advisory_lock_held() as advisory:
            run = backup_lab.start_run()
            try:
                seen = first_seen(
                    backup_lab,
                    "the control session waits for the advisory lock",
                    lambda: control_waits_for_the_advisory_lock(backup_lab),
                    120,
                )
                while time.monotonic() < seen + ADVISORY_FIRST:
                    assert run.running(), "the run ended while it waited for the advisory lock"
                    time.sleep(POLL_SECONDS)
                advisory.query(UNLOCK_BIGINT, k=str(KEY))
                released = time.monotonic()
                first_seen(
                    backup_lab,
                    f"the control session waits on {PROBE}",
                    lambda: control_waits_on(backup_lab, PROBE),
                    60,
                )
                ended = watch_until_exit(backup_lab, run, released + LATEST)
                assert not run.running(), f"the run still waits {LATEST:g} s after the grant"
            finally:
                if run.running():
                    end_the_run(backup_lab, run)
        result = run.wait(60)
    after_grant = ended - released
    assert EARLIEST <= after_grant <= LATEST, f"the run ended {after_grant:.1f} s after the grant"
    the_bound_failure(result)
    assert set_names(backup_lab.double) == before


# K-04 ----------------------------------------------------------------------------------------

DATABASES = ("eko", "keycloak")
STORED_TIMEOUTS = (
    "SELECT coalesce(r.rolname, '-') || ' ' || coalesce(d.datname, '-') || ' ' || c "
    "FROM pg_db_role_setting s LEFT JOIN pg_roles r ON r.oid = s.setrole "
    "LEFT JOIN pg_database d ON d.oid = s.setdatabase, unnest(s.setconfig) AS c "
    "WHERE split_part(c, '=', 1) IN ('lock_timeout', 'statement_timeout', 'transaction_timeout') "
    "AND (s.setrole = 0 OR r.rolname IN ('eko_backup', 'eko_app', 'eko_keycloak')) "
    "AND (s.setdatabase = 0 OR d.datname IN ('eko', 'keycloak'))"
)


def stored_timeouts(backup_lab: BackupLab) -> list[str]:
    """Timeout entries a role, a database or every role carries (ALTER ROLE / DATABASE)."""
    return [row[0] for row in backup_lab.sql(STORED_TIMEOUTS)]


def fresh_session_timeouts(backup_lab: BackupLab, role: str, database: str) -> list[str]:
    out = backup_lab.composition.compose(
        "exec", "-T", "postgres", "psql", "-X", "-At", "-F", " ", "-U", role, "-d", database,
        "-c", SHOW_TIMEOUTS,
    )  # fmt: skip
    return out.stdout.split()


def backup_environment_timeouts(backup_lab: BackupLab, database: str) -> list[str]:
    """A session opened from the `backup` service's environment, as the script opens its own
    (PGOPTIONS or any other libpq variable of that environment applies to it)."""
    out = backup_lab.composition.compose(
        "run", "--rm", "--no-deps", "-T", "backup", "sh", "-c",
        'PGPASSWORD="$BACKUP_DB_PASSWORD" exec psql -X -At -F " " -h postgres -U eko_backup '
        f'-d {database} -c "{SHOW_TIMEOUTS}"',
    )  # fmt: skip
    return out.stdout.split()


def timeout_problems(backup_lab: BackupLab) -> list[str]:
    problems = stored_timeouts(backup_lab)
    sessions = [("eko_backup", "eko"), ("eko_backup", "keycloak"), ("eko_app", "eko")]
    for role, database in sessions:
        shown = fresh_session_timeouts(backup_lab, role, database)
        if shown != ["0"] * len(TIMEOUTS):
            problems.append(f"{role}@{database} starts with {shown}")
    for database in DATABASES:
        shown = backup_environment_timeouts(backup_lab, database)
        if shown != ["0"] * len(TIMEOUTS):
            problems.append(f"backup's environment on {database} starts with {shown}")
    return problems


def test_eko120_k04_no_role_database_or_server_carries_a_lock_bound(
    backup_lab: BackupLab,
) -> None:
    assert timeout_problems(backup_lab) == []


PLANTED = {
    "role-eko_app": (
        "ALTER ROLE eko_app SET lock_timeout = '180s'",
        "ALTER ROLE eko_app RESET lock_timeout",
    ),
    "database-keycloak": (
        "ALTER DATABASE keycloak SET lock_timeout = '180s'",
        "ALTER DATABASE keycloak RESET lock_timeout",
    ),
}


@pytest.mark.parametrize("place", sorted(PLANTED))
def test_eko120_k04_contrast_a_planted_bound_is_reported(backup_lab: BackupLab, place: str) -> None:
    plant, reset = PLANTED[place]
    backup_lab.sql(plant)
    try:
        problems = timeout_problems(backup_lab)
    finally:
        backup_lab.sql(reset)
    assert any("lock_timeout=180s" in p for p in problems), problems
    assert any("3min" in p for p in problems), problems
    assert timeout_problems(backup_lab) == []
