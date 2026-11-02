"""K-05 / ADR-0004-C26, migrate half: a statement running past the 30 s statement timeout fails
the run with nothing changed; the same statement at 25 s passes.

Elapsed time is measured as in test_adr0004_c26_lock_timeout.py.
"""

import pytest

from tests.runtime.lab import Lab, MigrateRun
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
STATEMENT_TIMEOUT = 30.0
TOLERANCE = 0.5
MARGIN = 2.5


def granted(lab: Lab, run: MigrateRun) -> bool:
    identity = mc.pg_locks_identity(KEY)
    return any(lock[:3] == identity and lock[3] for lock in lab.advisory_locks(run))


def test_adr0004_c26_statement_timeout(lab: Lab) -> None:
    lab.at_head()
    image = lab.variant("sleep_35")
    before = lab.comparison_dump()
    run = lab.start_migrate(image)
    try:
        granted_at = lab.wait_until("advisory lock granted", lambda: granted(lab, run))
        code = run.wait(90)
        logs = run.logs()
        exited_at = run.exited_at[0]
    finally:
        run.remove()
    elapsed = exited_at - granted_at
    assert code != 0, logs
    assert '"cause":"psycopg.errors.QueryCanceled"' in logs, logs[-2000:]
    assert STATEMENT_TIMEOUT - TOLERANCE <= elapsed < STATEMENT_TIMEOUT + MARGIN, elapsed
    assert lab.comparison_dump() == before


def test_adr0004_c26_statement_timeout_contrast_a_25_second_statement_passes(lab: Lab) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(lab.variant("sleep_25"), timeout=90)
    assert code == 0, logs
    assert lab.versions() == ["t_sleep_25"]
    assert lab.comparison_dump() != before
