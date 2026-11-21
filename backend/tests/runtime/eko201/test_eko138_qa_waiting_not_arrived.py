"""EKO-1-38 K-02 (G-5 A), QA contrast: "in the waiting phase", not "reached the server".

The carrier's late request passes its two non-retried checkouts in a few milliseconds, faster than
one observation poll plus `block()`, so a condition counting requests that reached the server
passes it as well as one counting requests in the waiting phase. Here that request pauses
`GAP_SECONDS` between its `find` and its `refresh_holder` checkout
(`tests/support/qa138_slow_lock_app.py`); one element changes against the carrier's `[one-late]`
run. Blockers placed during the pause make the second checkout time out, so only an observation of
the waiting phase keeps the ten answers 200.
"""

import pytest

from app.data.database import POOL_TIMEOUT_SECONDS
from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.runtime.eko201.conftest import session_count
from tests.support import oidc_stub, qa138_slow_lock_app
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

SLOW_LOCK = "tests.support.qa138_slow_lock_app:create_with_blockers"
# The late request is sent this long after the midpoint of the sends' start and the refresh's
# (`k04.send_tagged`), earlier than the carrier's `k04.LATE_SECONDS`: its second checkout starts
# `GAP_SECONDS` later still and must time out inside the hold that ends 1.5 s after the sends.
LATE_SECONDS = 0.4
# `time.monotonic()` advances in ticks of about 16 ms on the Windows test host.
CLOCK_TICK = 0.05


def test_k02_late_request_paused_between_its_checkouts_is_waited_for_before_the_blockers(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    run = k04.pool_exhausted_responsive(pg, stub, k04.all_waiting, LATE_SECONDS, factory=SLOW_LOCK)
    process = "a" if k04.LATE_INDEX % 2 == 0 else "b"
    late = run.final[process]["requests"][str(k04.LATE_INDEX)]
    find, lock = late["checkouts"][:2]
    # Precondition: blockers placed during the pause would make the second checkout time out
    # inside the hold, so this run can tell the waiting phase from "reached the server" (R-01).
    assert k04.hold_after(run, lock) >= POOL_TIMEOUT_SECONDS, (run.final, run.marks)
    # The pause sat between the two checkouts, whatever the outcome (less the clock's ~16-ms tick).
    assert lock["started"] - find["ended"] >= qa138_slow_lock_app.GAP_SECONDS - CLOCK_TICK, late
    assert [o.status for o in run.outcomes] == [200] * 10, (run.outcomes, late)
    assert [(c["step"], c["outcome"]) for c in late["checkouts"]] == [
        ("find", "ok"),
        ("refresh_holder", "lock taken"),
    ], late
    assert len(stub.refreshes(run.sid)) == 1
    assert stub.superseded_uses() == []
    assert session_count(pg) == 1
    assert run.refresh_at_block == [None], run.marks
    full = k04.pools_full(run)
    assert all(c == p and h == p for c, h, p in full.values()), full
