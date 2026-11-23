"""EKO-1-40 K-01 (#228): a controlled checkout delay on the refresh holder's process makes the
pool-exhausted carrier, as it is at `b099acc`, answer 503 from a `find` before any blocker.

The carrier body runs unchanged on `tests.support.eko140_checkout_delay:create_delayed_on_holder`:
once a request of a process holds the session's refresh lock, every session-store checkout of that
process keeps its connection `DELAY_SECONDS` longer. The holder's process has one free connection
(pool 2, overflow 0); the other requests' `find` and `refresh_holder` checkouts and every waiter's
probe queue on it, and a `find`, which the application does not retry, gives up after
`POOL_TIMEOUT_SECONDS`. The verdict is signature S read from both processes' records
(`tests.support.eko140_signature`), not merely a red: a run with S cannot have nine requests
waiting, so the carrier stops inside `all_waiting`, and the record is read there.
"""

from typing import Any

import pytest

from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.runtime.eko201.processes import Backend
from tests.support import oidc_stub
from tests.support.eko140_checkout_delay import DELAY_SECONDS
from tests.support.eko140_signature import holder_process, signature_s
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

ON_HOLDER = "tests.support.eko140_checkout_delay:create_delayed_on_holder"
# `(a, b) * 5`: the odd indices go to process b.
B_FIRST = 1

Record = dict[str, dict[str, Any]]


def recorded(record: Record) -> k04.Settle:
    """The carrier's `all_waiting`; when it fails, both processes' records are kept first."""

    def settle(stub: oidc_stub.Stub, sid: str, a: Backend, b: Backend) -> tuple[Backend, Backend]:
        try:
            return k04.all_waiting(stub, sid, a, b)
        except AssertionError:
            record.update(a=k04.observed(a), b=k04.observed(b))
            raise

    return settle


def assert_signature_s(record: Record, red: pytest.ExceptionInfo[AssertionError]) -> str:
    """S, with the delay in effect on the holder's process only; returns the holder's process."""
    assert record, f"the run went red before or after the settle: {red.value}"
    holder = holder_process(record)
    assert holder is not None, record
    [other] = {"a", "b"} - {holder}
    # The delay was in effect on the holder's process only.
    delay = record[holder]["delay"]
    assert (delay["on"], delay["seconds"]) == ("holder", DELAY_SECONDS), delay
    assert delay["applied"] > 0, delay
    assert record[other]["delay"]["applied"] == 0, record[other]["delay"]
    hits = signature_s(record)
    assert hits, (str(red.value), record)
    return holder


@pytest.mark.parametrize("late", [None, k04.LATE_SECONDS], ids=["on-time", "one-late"])
def test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker(
    pg: Postgres, stub: oidc_stub.Stub, late: float | None
) -> None:
    record: Record = {}
    with pytest.raises(AssertionError) as red:
        k04.pool_exhausted_responsive(pg, stub, recorded(record), late, ON_HOLDER)
    assert_signature_s(record, red)


def test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find(
    pg: Postgres, stub: oidc_stub.Stub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The K-01 edge "holder on b". Left to the race, the holder is on process a in every delayed
    run recorded for EKO-1-40 (its pool is warm from the login), so the twin is forced as
    EKO-1-38's `test_eko138_qa_holder_on_b.py` forces it: request 1 (process b) is sent first and
    every other request once that refresh reached the identity server. That send order is the one
    element changed against the carrier body."""
    send = k04.send_tagged

    def b_first(
        target: Backend,
        session: str,
        tag: int,
        at: oidc_stub.Stub,
        late: float | None,
        sends_started: float | None = None,
    ) -> k04.Outcome:
        return send(target, session, tag, at, None if tag == B_FIRST else 0.0)

    monkeypatch.setattr(k04, "send_tagged", b_first)
    record: Record = {}
    with pytest.raises(AssertionError) as red:
        k04.pool_exhausted_responsive(pg, stub, recorded(record), None, ON_HOLDER)
    assert assert_signature_s(record, red) == "b", record
