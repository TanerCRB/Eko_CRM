"""EKO-2-01 K-04 (ADR-0003-C18, ADR-0002-C16): concurrent expired-token requests across backend
processes share one bounded refresh per session, also with the connection pool exhausted.

Two uvicorn processes, each its own pool of 2, against real PostgreSQL and the OIDC stub. Latency
is measured from each request's own send time. Timing holds for this test host only.
"""

import dataclasses
import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
import pytest

from app.data.database import POOL_TIMEOUT_SECONDS
from tests.runtime.eko201.conftest import SESSION_COOKIE, session_count
from tests.runtime.eko201.processes import Backend, backends, expired_login, expired_logins
from tests.support import eko138_observed_app, oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

logger = logging.getLogger(__name__)
# The run record is INFO; pytest's captured-log section shows it with a failing test only.
logger.setLevel(logging.INFO)

BOUND = 6.0
BLOCKERS = "tests.support.eko201_fixture_app:create_with_blockers"
UNBOUNDED = "tests.support.eko201_fixture_app:create_unbounded_with_blockers"
OBSERVED = "tests.support.eko138_observed_app:create_with_blockers"
# EKO-1-38: the one late request of the pool-exhausted carrier, sent at the later of
# `LATE_AFTER_START` after the ten sends began and `LATE_SECONDS` after the holder's refresh
# reached the identity server: past the old 0.2-s settle and its blockers, and, unless that
# refresh starts late, early enough that a bounded checkout started then times out before the
# hold ends 1.5 s after the sends began (Reviewer R-01). Tests relying on that timeout ending
# inside the hold assert it.
LATE_INDEX = 6
LATE_SECONDS = 0.35
LATE_AFTER_START = 0.5
WAITERS = 9


@dataclass
class Outcome:
    status: int | None
    seconds: float


def send(target: Backend, session: str, timeout: float = 40) -> Outcome:
    started = time.monotonic()
    try:
        status: int | None = target.get("/api/auth/session", session, timeout=timeout).status_code
    except httpx.TimeoutException:
        status = None
    return Outcome(status, time.monotonic() - started)


def concurrently(calls: list[Callable[[], Outcome]]) -> list[Outcome]:
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(lambda call: call(), calls))


def expired_session(stub: oidc_stub.Stub, target: Backend) -> tuple[str, str]:
    session = expired_login(stub, target)
    [sid] = [s for s in stub.sessions if stub.sso_alive(s)][-1:]
    return session, sid


def wait_for_refresh(stub: oidc_stub.Stub, count: int = 1) -> None:
    deadline = time.monotonic() + 10
    while len(stub.refreshes()) < count:
        assert time.monotonic() < deadline, "no refresh reached the identity server"
        time.sleep(0.02)


def block(target: Backend, count: int) -> None:
    held = httpx.get(f"{target.url}/__eko201/block", params={"count": count}, timeout=20)
    assert held.text == str(count), held.text


def release(target: Backend) -> None:
    httpx.get(f"{target.url}/__eko201/release", timeout=20)


def test_k04_ten_concurrent_requests_share_one_refresh(pg: Postgres, stub: oidc_stub.Stub) -> None:
    with backends(pg, stub) as (a, b):
        session, sid = expired_session(stub, a)
        stub.refresh_delay_seconds = 1.0
        outcomes = concurrently([partial(send, t, session) for t in (a, b) * 6])
    assert [o.status for o in outcomes] == [200] * 12, outcomes
    assert len(stub.refreshes(sid)) == 1
    assert stub.superseded_uses() == []
    assert session_count(pg) == 1


def test_k04_one_request_refreshes_once(pg: Postgres, stub: oidc_stub.Stub) -> None:
    with backends(pg, stub, count=1) as (a,):
        session, sid = expired_session(stub, a)
        assert send(a, session).status == 200
        assert len(stub.refreshes(sid)) == 1
        assert send(a, session).status == 200
    assert len(stub.refreshes(sid)) == 1


def test_k04_hanging_identity_server_gives_every_request_503_within_six_seconds(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    with backends(pg, stub) as (a, b):
        session, sid = expired_session(stub, a)
        stub.refresh_mode = "hang"
        outcomes = concurrently([partial(send, t, session) for t in (a, b) * 5])
        stub.release.set()
    assert [o.status for o in outcomes] == [503] * 10, outcomes
    assert max(o.seconds for o in outcomes) < BOUND, outcomes
    assert len(stub.refreshes(sid)) == 1
    assert session_count(pg) == 1


def _pool_exhausted_hang(
    pg: Postgres, stub: oidc_stub.Stub, factory: str
) -> tuple[list[Outcome], str]:
    with backends(pg, stub, factory=factory) as (a, b):
        session, sid = expired_session(stub, a)
        stub.refresh_mode = "hang"
        results: list[Outcome] = []
        holder = threading.Thread(target=lambda: results.append(send(a, session)))
        holder.start()
        wait_for_refresh(stub)
        block(a, 1)
        block(b, 2)
        try:
            results += concurrently([partial(send, t, session) for t in (a, b) * 5])
        finally:
            holder.join(timeout=60)
            stub.release.set()
            release(a)
            release(b)
    return results, sid


def test_k04_pool_exhausted_hanging_identity_server_still_answers_503_within_six_seconds(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    outcomes, sid = _pool_exhausted_hang(pg, stub, BLOCKERS)
    assert len(stub.refreshes(sid)) == 1
    assert session_count(pg) == 1
    assert len(outcomes) == 11
    assert [o.status for o in outcomes] == [503] * 11, outcomes
    assert max(o.seconds for o in outcomes) < BOUND, outcomes


def test_k04_opposite_without_the_checkout_bound_exceeds_six_seconds(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    """Recorded, not inferred: the same carrier with SQLAlchemy's default checkout wait."""
    # Requests freed late by the 30-second checkout wait may start later refreshes of their own;
    # only the lateness is this case's claim.
    outcomes, _ = _pool_exhausted_hang(pg, stub, UNBOUNDED)
    waiters = outcomes[1:]
    late = [o for o in waiters if o.status is None or o.seconds >= BOUND]
    record = [(o.status, round(o.seconds, 2)) for o in outcomes]
    print(f"EKO-2-01 K-04 opposite: {record}")  # noqa: T201  # leftovers-allow: the recorded opposite (C16)
    assert late, outcomes


def observed(target: Backend) -> dict[str, Any]:
    """What the process records about its pool, its blockers and each tagged request."""
    url = target.url + eko138_observed_app.STATE_PATH
    found: dict[str, Any] = httpx.get(url, timeout=20).json()
    return found


def send_tagged(
    target: Backend,
    session: str,
    tag: int,
    stub: oidc_stub.Stub,
    late: float | None,
    not_before: float | None = None,
) -> Outcome:
    """`send`, tagged for the process's record; a late one is sent `late` seconds after the
    first refresh reached the identity server, and not before the instant `not_before` (EKO-1-38):
    anchored on the refresh and the sends, never on the blockers, which under the observed settle
    wait for this request."""
    if late is not None:
        wait_for_refresh(stub)
        at = max(stub.refreshes()[0].started + late, not_before or 0.0)
        time.sleep(max(0.0, at - time.monotonic()))
    started = time.monotonic()
    headers = {"cookie": f"{SESSION_COOKIE}={session}", eko138_observed_app.TAG_HEADER: str(tag)}
    try:
        status: int | None = httpx.get(
            target.url + "/api/auth/session", headers=headers, timeout=40
        ).status_code
    except httpx.TimeoutException:
        status = None
    return Outcome(status, time.monotonic() - started)


def holder_first(a: Backend, b: Backend) -> tuple[Backend, Backend]:
    """The process whose request is refreshing, then the other one."""
    phases = [[r["phase"] for r in observed(t)["requests"].values()] for t in (a, b)]
    return (a, b) if "holding" in phases[0] else (b, a)


def fixed_settle(stub: oidc_stub.Stub, sid: str, a: Backend, b: Backend) -> tuple[Backend, Backend]:
    """The settle before EKO-1-38: the refresh reached the identity server, then 0.2 s."""
    wait_for_refresh(stub)
    time.sleep(0.2)
    return holder_first(a, b)


def all_waiting(stub: oidc_stub.Stub, sid: str, a: Backend, b: Backend) -> tuple[Backend, Backend]:
    """Until the holder's refresh is unanswered at the identity server and every other request is
    past its non-retried checkouts, in the waiting phase (EKO-1-38 K-02, G-5 A)."""
    deadline = time.monotonic() + 10
    while True:
        calls = stub.refreshes(sid)
        refreshes = [c.finished for c in calls]
        snapshots = {t.url: observed(t) for t in (a, b)}
        states = {url: snapshot["requests"] for url, snapshot in snapshots.items()}
        tagged = {url: {k: r["phase"] for k, r in s.items()} for url, s in states.items()}
        phases = {url: list(p.values()) for url, p in tagged.items()}
        holding = {url: p.count("holding") for url, p in phases.items()}
        waiting = sum(p.count("waiting") for p in phases.values())
        if refreshes == [None] and sum(holding.values()) == 1 and waiting == WAITERS:
            return (a, b) if holding[a.url] else (b, a)
        spans = [(c.started, c.finished) for c in calls]
        pools = {url: snapshot["checked_out"] for url, snapshot in snapshots.items()}
        behind = {k: r for s in states.values() for k, r in s.items() if r["phase"] != "waiting"}
        missing = (
            f"refresh {spans} at {time.monotonic():.3f}: {tagged}; "
            f"not waiting: {behind}; checked out: {pools}"
        )
        assert refreshes in ([], [None]), f"refresh ended before all waited: {missing}"
        assert time.monotonic() < deadline, f"not all requests waiting: {missing}"
        time.sleep(0.02)


Settle = Callable[[oidc_stub.Stub, str, Backend, Backend], tuple[Backend, Backend]]


@dataclass
class Run:
    outcomes: list[Outcome]
    sid: str
    # Read after both blockers answered: the refresh's `finished` and each process's record.
    refresh_at_block: list[float | None]
    at_block: dict[str, dict[str, Any]]
    # Read after the release, before the processes stop.
    final: dict[str, dict[str, Any]]
    # The test's own instants: the sends, the settle's end, both blockers answered.
    marks: dict[str, float]


def pool_exhausted_responsive(
    pg: Postgres, stub: oidc_stub.Stub, settle: Settle, late: float | None, factory: str = OBSERVED
) -> Run:
    with backends(pg, stub, factory=factory) as (a, b):
        session, sid = expired_session(stub, a)
        stub.refresh_delay_seconds = 2.0
        with ThreadPoolExecutor(max_workers=10) as pool:
            started = time.monotonic()
            not_before = started + LATE_AFTER_START
            futures = [
                pool.submit(send_tagged, t, session, i, stub, late, not_before)
                if i == LATE_INDEX
                else pool.submit(send_tagged, t, session, i, stub, None)
                for i, t in enumerate((a, b) * 5)
            ]
            holder, other = settle(stub, sid, a, b)
            settled = time.monotonic()
            block(holder, 1)
            block(other, 2)
            refresh_at_block = [c.finished for c in stub.refreshes(sid)]
            marks = {"started": started, "settled": settled, "blocked": time.monotonic()}
            at_block = {"a": observed(a), "b": observed(b)}
            time.sleep(max(0.0, 1.5 - (time.monotonic() - started)))
            release(a)
            release(b)
            outcomes = [f.result() for f in futures]
        final = {"a": observed(a), "b": observed(b)}
    run = Run(outcomes, sid, refresh_at_block, at_block, final, marks)
    # Shown with a failing test's report, so a red run can be attributed (Reviewer R-02).
    logger.info("pool-exhausted run record: %s", json.dumps(dataclasses.asdict(run)))
    return run


def hold_after(run: Run, checkout: dict[str, Any]) -> float:
    """Seconds the late request's process still held its blockers after the checkout started."""
    process = "a" if LATE_INDEX % 2 == 0 else "b"
    released: float = run.final[process]["released_at"]
    return released - float(checkout["started"])


def late_request(run: Run) -> dict[str, Any]:
    process = "a" if LATE_INDEX % 2 == 0 else "b"
    found: dict[str, Any] = run.final[process]["requests"][str(LATE_INDEX)]
    return found


def pools_full(run: Run) -> dict[str, tuple[int, int, int]]:
    """Per process, at block: (checked out, blockers plus refreshing requests, pool size)."""
    found = {}
    for name, state in run.at_block.items():
        holding = [r for r in state["requests"].values() if r["phase"] == "holding"]
        found[name] = (state["checked_out"], state["held"] + len(holding), state["pool_size"])
    return found


@pytest.mark.parametrize("late", [None, LATE_SECONDS], ids=["on-time", "one-late"])
def test_k04_pool_exhausted_responsive_identity_server_serves_every_request(
    pg: Postgres, stub: oidc_stub.Stub, late: float | None
) -> None:
    run = pool_exhausted_responsive(pg, stub, all_waiting, late)
    if late is not None:
        # Precondition: a bounded checkout started when the late request did would have timed
        # out inside the hold, so this run could tell a waited-for request from a blocked one.
        first = late_request(run)["checkouts"][0]
        assert hold_after(run, first) >= POOL_TIMEOUT_SECONDS, (run.final, run.marks)
    outcomes, sid = run.outcomes, run.sid
    assert [o.status for o in outcomes] == [200] * 10, outcomes
    assert len(stub.refreshes(sid)) == 1
    assert stub.superseded_uses() == []
    assert session_count(pg) == 1
    # EKO-1-38 K-03: the pools were exhausted while the refresh was still unanswered.
    refresh = [(c.started, c.finished) for c in stub.refreshes(sid)]
    assert run.refresh_at_block == [None], (refresh, run.marks)
    full = pools_full(run)
    assert all(c == p and h == p for c, h, p in full.values()), full


def test_k04_two_sessions_refresh_independently(pg: Postgres, stub: oidc_stub.Stub) -> None:
    with backends(pg, stub) as (a, b):
        first, second = expired_logins(stub, [a, b])
        stub.refresh_delay_seconds = 2.0
        started = time.monotonic()
        outcomes = concurrently([lambda: send(a, first), lambda: send(b, second)])
        elapsed = time.monotonic() - started
    assert [o.status for o in outcomes] == [200, 200]
    assert elapsed < 3.5, elapsed
    assert len(stub.refreshes()) == 2
    assert {c.sid for c in stub.refreshes()} == set(stub.sessions)
