"""K-01: while another session holds the advisory lock recorded in compose.yaml, migrate reads no
revision and applies no DDL; it waits with no time limit (35 s here, past the 30 s statement
timeout) and then applies its revision. The key is read from compose.yaml, never written here.

Contrast: a different key, or the same number in the two-`integer` form, is another lock.
"""

import time

import pytest

from tests.runtime.lab import Lab, MigrateRun, PsqlSession
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
HOLD_SECONDS = 35
DUMP_EVERY_SECONDS = 3
LOCK_BIGINT = "SELECT pg_advisory_lock(CAST(:'k' AS bigint))"
UNLOCK_BIGINT = "SELECT pg_advisory_unlock(CAST(:'k' AS bigint))"
LOCK_TWO_INTEGERS = "SELECT pg_advisory_lock(CAST(:'hi' AS integer), CAST(:'lo' AS integer))"


def waiting_for_the_recorded_lock(lab: Lab, run: MigrateRun) -> bool:
    identity = mc.pg_locks_identity(KEY)
    return any(lock[:3] == identity and not lock[3] for lock in lab.advisory_locks(run))


def test_adr0004_c26_advisory_lock_shared(lab: Lab) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    holder = PsqlSession(lab.composition, name="eko-test-holder")
    run: MigrateRun | None = None
    try:
        holder.query(LOCK_BIGINT, k=str(KEY))
        held_at = time.monotonic()
        started = run = lab.start_migrate(lab.variant("next"))
        lab.wait_until(
            "migrate waits for the lock", lambda: waiting_for_the_recorded_lock(lab, started)
        )
        while time.monotonic() < held_at + HOLD_SECONDS:
            assert run.running(), run.logs()
            assert lab.relation_locks(run) == [], "migrate touched a table before the lock"
            assert lab.comparison_dump() == before
            time.sleep(DUMP_EVERY_SECONDS)
        assert waiting_for_the_recorded_lock(lab, run)
        holder.query(UNLOCK_BIGINT, k=str(KEY))
        code = run.wait(60)
        logs = run.logs()
    finally:
        holder.close()
        if run is not None:
            run.remove()
    assert code == 0, logs
    assert lab.versions() == ["t_next"]
    assert lab.lineage() == {"0001", "0002", "t_next"}
    assert lab.comparison_dump() != before


@pytest.mark.parametrize("form", ["another-key", "two-integer-form"])
def test_adr0004_c26_contrast_another_lock_does_not_hold_migrate_back(lab: Lab, form: str) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    holder = PsqlSession(lab.composition, name="eko-test-other-lock")
    try:
        if form == "another-key":
            other = KEY + 1 if KEY < 2**63 - 1 else KEY - 1
            holder.query(LOCK_BIGINT, k=str(other))
        else:
            high, low = mc.two_integer_form(KEY)
            holder.query(LOCK_TWO_INTEGERS, hi=str(high), lo=str(low))
        code, logs = lab.run_migrate(lab.variant("next"), timeout=60)
        [[still_held]] = lab.sql(
            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE l.locktype = 'advisory' AND l.granted AND a.application_name = :'name'",
            name=holder.application_name,
        )
    finally:
        holder.close()
    assert still_held == "1"
    assert code == 0, logs
    assert lab.versions() == ["t_next"]
    assert lab.comparison_dump() != before
