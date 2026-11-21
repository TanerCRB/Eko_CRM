"""EKO-1-38 K-01: the pool-exhausted carrier's fixed 0.2-s settle, with one request late.

The late request is sent `k04.LATE_SECONDS` after the holder's refresh reached the identity
server; under the fixed settle the blockers are in place by then, so its first checkout, a
non-retried one, waits the pool timeout and the request answers 503. Every instant compared here
is read from the same backend process's record (`tests/support/eko138_observed_app.py`).
"""

import pytest

from app.data.database import POOL_TIMEOUT_SECONDS
from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

# Slack for "within roughly the pool timeout": the request's own work after the checkout failed.
ANSWER_SLACK_SECONDS = 0.5


def test_k01_fixed_settle_answers_503_to_the_late_request_from_its_bounded_checkout(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    run = k04.pool_exhausted_responsive(pg, stub, k04.fixed_settle, k04.LATE_SECONDS)
    statuses = [o.status for o in run.outcomes]
    expected = [503 if i == k04.LATE_INDEX else 200 for i in range(10)]
    assert statuses == expected, run.outcomes
    process = "a" if k04.LATE_INDEX % 2 == 0 else "b"
    state = run.final[process]
    late = state["requests"][str(k04.LATE_INDEX)]
    first = late["checkouts"][0]
    # The first checkout started while the blockers held, and timed out after the full bound.
    assert state["held_at"] <= first["started"] < state["released_at"], (state, late)
    assert (first["step"], first["outcome"]) == ("find", "unavailable"), late
    assert first["ended"] - first["started"] >= POOL_TIMEOUT_SECONDS, late
    assert late["status"] == 503, late
    assert late["answered"] - first["started"] < POOL_TIMEOUT_SECONDS + ANSWER_SLACK_SECONDS, late
    assert len(late["checkouts"]) == 1, late
