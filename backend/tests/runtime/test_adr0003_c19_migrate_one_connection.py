"""K-06 / ADR-0003-C19: a migrate run holds exactly one database connection, counted in
pg_stat_activity at two moments: while it waits for the advisory lock a direct session holds, and
while the slow test-only revision `t_slow` applies DDL. test_k03_roles_and_budget.py counts
migrate's connection as a constant and cannot see this.
"""

import pytest

from tests.runtime.lab import VARIANTS, Lab, MigrateRun, PsqlSession
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
LOCK_CALL = "take_migration_lock(connection,"


def waiting(lab: Lab, run: MigrateRun) -> bool:
    identity = mc.pg_locks_identity(KEY)
    return any(lock[:3] == identity and not lock[3] for lock in lab.advisory_locks(run))


def in_ddl(lab: Lab, run: MigrateRun) -> bool:
    return any("pg_sleep" in query for _, _, query in lab.activity(run))


def count_at_two_moments(lab: Lab, image: str) -> tuple[int, int, int, str]:
    lab.at_head()
    holder = PsqlSession(lab.composition, name="eko-test-budget-holder")
    run = None
    try:
        holder.query("SELECT pg_advisory_lock(CAST(:'k' AS bigint))", k=str(KEY))
        started = run = lab.start_migrate(image)
        lab.wait_until("migrate waits for the advisory lock", lambda: waiting(lab, started))
        waiting_count = lab.migrate_sessions(run)
        holder.query("SELECT pg_advisory_unlock(CAST(:'k' AS bigint))", k=str(KEY))
        lab.wait_until("migrate applies the slow revision", lambda: in_ddl(lab, started))
        applying_count = lab.migrate_sessions(run)
        code = run.wait(60)
        logs = run.logs()
    finally:
        holder.close()
        if run is not None:
            run.remove()
    return waiting_count, applying_count, code, logs


def test_adr0003_c19_migrate_one_connection(lab: Lab) -> None:
    waiting_count, applying_count, code, logs = count_at_two_moments(lab, lab.variant("slow"))
    assert code == 0, logs
    assert (waiting_count, applying_count) == (1, 1)


def test_adr0003_c19_contrast_a_planted_second_connection_is_counted(lab: Lab) -> None:
    # Planted contrast: the lock taken on a second connection of the same engine, kept referenced
    # so it stays open for the whole run.
    planted = "take_migration_lock(held := engine.connect(),"
    image = lab.planted_env_py("second_connection", LOCK_CALL, planted, VARIANTS["slow"])
    waiting_count, applying_count, _, logs = count_at_two_moments(lab, image)
    assert waiting_count == 2, logs
    assert applying_count == 2, logs
