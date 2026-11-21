"""EKO-1-38 K-01: the pool-exhausted carrier's fixed 0.2-s settle, with one request late.

The late request is sent at the later of `k04.LATE_AFTER_START` after the ten sends began and
`k04.LATE_SECONDS` after the holder's refresh reached the identity server (`k04.send_tagged`);
under the fixed settle the blockers are in place by then, so its first checkout, a non-retried
one, waits the pool timeout and the request answers 503. Every instant compared within the
backend's record is read from the same backend process (`tests/support/eko138_observed_app.py`).

`refresh-late` repeats the run with the holder's refresh reaching the identity server
`REFRESH_LAG_SECONDS` later than usual: the hold still ends 1.5 s after the sends began (a K-04
guarded line), so the late request's timing must not depend on when the refresh started (R-01).
"""

import pytest

from app.data.database import POOL_TIMEOUT_SECONDS
from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.support import eko138_observed_app, oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

# Slack for "within roughly the pool timeout": the request's own work after the checkout failed.
ANSWER_SLACK_SECONDS = 0.5
LATE_REFRESH = "tests.support.eko138_observed_app:create_with_late_refresh"


@pytest.mark.parametrize(
    ("factory", "lag"),
    [(k04.OBSERVED, 0.0), (LATE_REFRESH, eko138_observed_app.REFRESH_LAG_SECONDS)],
    ids=["refresh-on-time", "refresh-late"],
)
def test_k01_fixed_settle_answers_503_to_the_late_request_from_its_bounded_checkout(
    pg: Postgres, stub: oidc_stub.Stub, factory: str, lag: float
) -> None:
    run = k04.pool_exhausted_responsive(pg, stub, k04.fixed_settle, k04.LATE_SECONDS, factory)
    [refresh] = stub.refreshes(run.sid)
    assert refresh.started - run.marks["started"] >= lag, (refresh, run.marks)
    process = "a" if k04.LATE_INDEX % 2 == 0 else "b"
    state = run.final[process]
    late = state["requests"][str(k04.LATE_INDEX)]
    first = late["checkouts"][0]
    # Precondition: the first checkout started while the blockers held, and the hold outlasted
    # the checkout bound from that instant, so a bounded checkout times out inside it.
    assert state["held_at"] <= first["started"], (state, late)
    assert state["released_at"] - first["started"] >= POOL_TIMEOUT_SECONDS, (state, late)
    statuses = [o.status for o in run.outcomes]
    expected = [503 if i == k04.LATE_INDEX else 200 for i in range(10)]
    assert statuses == expected, run.outcomes
    assert (first["step"], first["outcome"]) == ("find", "unavailable"), late
    assert first["ended"] - first["started"] >= POOL_TIMEOUT_SECONDS, late
    assert late["status"] == 503, late
    assert late["answered"] - first["started"] < POOL_TIMEOUT_SECONDS + ANSWER_SLACK_SECONDS, late
    assert len(late["checkouts"]) == 1, late
