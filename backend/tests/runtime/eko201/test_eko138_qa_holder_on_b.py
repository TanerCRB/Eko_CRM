"""EKO-1-38 K-03 (G-3 A), QA contrast: the refresh holder on process b.

The pool-exhausted carrier places its blockers by the process observed to hold the refresh
(`block(holder, 1)`, `block(other, 2)`). Left to the race, the holder is on process a in most runs,
where those counts equal the literal `block(a, 1)`, `block(b, 2)` of the body before EKO-1-38, so
the carrier alone does not show that the counts follow the holder. Here the twin case is forced:
request 1 (process b) is sent first and every other request only once that refresh reached the
identity server. One element changes against the carrier's on-time run: which process holds.
"""

import pytest

from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.runtime.eko201.conftest import session_count
from tests.runtime.eko201.processes import Backend
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

# `(a, b) * 5`: the odd indices go to process b.
FIRST = 1


def test_k03_holder_on_process_b_still_exhausts_both_pools_while_the_refresh_is_unanswered(
    pg: Postgres, stub: oidc_stub.Stub, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = k04.send_tagged

    def b_first(
        target: Backend, session: str, tag: int, at: oidc_stub.Stub, late: float | None
    ) -> k04.Outcome:
        return send(target, session, tag, at, None if tag == FIRST else 0.0)

    monkeypatch.setattr(k04, "send_tagged", b_first)
    run = k04.pool_exhausted_responsive(pg, stub, k04.all_waiting, None)
    # Read after the release, so the precondition holds whenever the blockers were placed.
    held = {
        name: [tag for tag, r in state["requests"].items() if r["phase"] == "held"]
        for name, state in run.final.items()
    }
    assert held == {"a": [], "b": [str(FIRST)]}, held
    assert [o.status for o in run.outcomes] == [200] * 10, run.outcomes
    assert len(stub.refreshes(run.sid)) == 1
    assert stub.superseded_uses() == []
    assert session_count(pg) == 1
    refresh = [(c.started, c.finished) for c in stub.refreshes(run.sid)]
    assert run.refresh_at_block == [None], (refresh, run.marks)
    full = k04.pools_full(run)
    assert all(c == p and h == p for c, h, p in full.values()), full
