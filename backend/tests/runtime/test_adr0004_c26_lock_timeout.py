"""K-05 / ADR-0004-C26, migrate half: once migrate holds the advisory lock, a table-lock wait
longer than 5 s fails the run with nothing changed, an application-role read of the contended table
waits no longer than that, and the running backend keeps answering.

The conflicting session holds only a read lock (an open transaction that has read the table), so
a delayed read can come only from migrate's queued exclusive request. Elapsed time is measured on
this host's monotonic clock, from the first poll that sees migrate's advisory lock granted to the
moment `docker wait` returns.
"""

import time

import pytest

from tests.runtime.lab import Lab, MigrateRun, PsqlSession, restart_count
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
LOCK_TIMEOUT = 5.0
# Below LOCK_TIMEOUT, so 5 s and 10 s (or 2 s) are told apart.
TOLERANCE = 0.5
MARGIN = 2.5
AT_ONCE = 1.0
READ = "SELECT count(*) FROM eko_test_contended"

APP_ENGINE_TIMEOUTS = """
from sqlalchemy import text
from app.core.settings import Settings, load_settings
from app.data.database import create_app_engine
engine = create_app_engine(load_settings(Settings))
with engine.connect() as connection:
    row = connection.execute(text(
        "SELECT current_setting('lock_timeout'), current_setting('statement_timeout')"
    )).one()
engine.dispose()
print(row[0], row[1])  # leftovers-allow: runs in the backend container; stdout is its answer
"""


def granted(lab: Lab, run: MigrateRun) -> bool:
    identity = mc.pg_locks_identity(KEY)
    return any(lock[:3] == identity and lock[3] for lock in lab.advisory_locks(run))


def waits_for_a_table_lock(lab: Lab, run: MigrateRun) -> bool:
    return any(w == "Lock" and "ALTER TABLE" in q for w, _, q in lab.activity(run))


def with_contended_table(lab: Lab) -> None:
    lab.at_head()
    owner = PsqlSession(lab.composition, role="eko_app", name="eko-test-owner")
    try:
        owner.query("CREATE TABLE eko_test_contended (id integer)")
    finally:
        owner.close()


def test_adr0004_c26_lock_timeout(lab: Lab) -> None:
    container = lab.serving_backend()
    restarts = restart_count(container)
    with_contended_table(lab)
    image = lab.variant("c26_alter")
    before = lab.comparison_dump()
    holder = PsqlSession(lab.composition, role="eko_app", name="eko-test-reader-holder")
    reader = PsqlSession(lab.composition, role="eko_app", name="eko-test-rep-read")
    holder.query("BEGIN")
    holder.query(READ)
    watch = lab.watch_health(20)
    run = lab.start_migrate(image)
    try:
        granted_at = lab.wait_until("advisory lock granted", lambda: granted(lab, run))
        lab.wait_until("migrate waits for the table", lambda: waits_for_a_table_lock(lab, run), 4)
        read_started = time.monotonic()
        read_done, read_lines = reader.wait(reader.send(READ), 30)
        code = run.wait(30)
        logs = run.logs()
        exited_at = run.exited_at[0]
    finally:
        holder.close()
        run.remove()
    try:
        after_started = time.monotonic()
        after_done, _ = reader.wait(reader.send(READ), 30)
    finally:
        reader.close()
    statuses = watch.statuses()
    elapsed = exited_at - granted_at
    assert code != 0, logs
    assert "lock timeout" in logs, logs[-2000:]
    assert LOCK_TIMEOUT - TOLERANCE <= elapsed < LOCK_TIMEOUT + MARGIN, elapsed
    assert read_lines == ["0"]
    assert read_done - read_started < LOCK_TIMEOUT + MARGIN
    assert after_done - after_started < AT_ONCE
    assert lab.comparison_dump() == before
    assert statuses and set(statuses) == {"200"}, statuses
    assert lab.composition.container_id("backend") == container
    assert restart_count(container) == restarts


def test_adr0004_c26_lock_timeout_contrast_without_the_conflicting_transaction(lab: Lab) -> None:
    with_contended_table(lab)
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(lab.variant("c26_alter"))
    assert code == 0, logs
    assert lab.versions() == ["t_c26_alter"]
    assert lab.comparison_dump() != before


def test_adr0004_c26_application_sessions_keep_the_server_default_timeouts(lab: Lab) -> None:
    lab.serving_backend()
    session = PsqlSession(lab.composition, role="eko_app", name="eko-test-defaults")
    try:
        direct = session.query(
            "SELECT current_setting('lock_timeout'), current_setting('statement_timeout')"
        )
    finally:
        session.close()
    probe = lab.composition.python_in_backend(APP_ENGINE_TIMEOUTS)
    assert direct == [["0", "0"]]
    assert probe.returncode == 0, probe.stderr[-2000:]
    assert probe.stdout.split() == ["0", "0"]
