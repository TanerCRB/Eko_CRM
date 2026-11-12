"""EKO-2-01 K-04 (ADR-0003-C18, ADR-0002-C16): concurrent expired-token requests across backend
processes share one bounded refresh per session, also with the connection pool exhausted.

Two uvicorn processes, each its own pool of 2, against real PostgreSQL and the OIDC stub. Latency
is measured from each request's own send time. Timing holds for this test host only.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import httpx
import pytest

from tests.runtime.eko201.conftest import session_count
from tests.runtime.eko201.processes import Backend, backends, login
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

BOUND = 6.0
BLOCKERS = "tests.support.eko201_fixture_app:create_with_blockers"
UNBOUNDED = "tests.support.eko201_fixture_app:create_unbounded_with_blockers"


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
    stub.access_lifespan_seconds = 1
    session = login(target)
    [sid] = [s for s in stub.sessions if stub.sso_alive(s)][-1:]
    stub.access_lifespan_seconds = 240
    time.sleep(1.3)
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


def test_k04_ten_concurrent_requests_share_one_refresh(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
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


def test_k04_pool_exhausted_responsive_identity_server_serves_every_request(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    with backends(pg, stub, factory=BLOCKERS) as (a, b):
        session, sid = expired_session(stub, a)
        stub.refresh_delay_seconds = 2.0
        with ThreadPoolExecutor(max_workers=10) as pool:
            started = time.monotonic()
            futures = [pool.submit(send, t, session) for t in (a, b) * 5]
            wait_for_refresh(stub)
            time.sleep(0.2)
            block(a, 1)
            block(b, 2)
            time.sleep(max(0.0, 1.5 - (time.monotonic() - started)))
            release(a)
            release(b)
            outcomes = [f.result() for f in futures]
    assert [o.status for o in outcomes] == [200] * 10, outcomes
    assert len(stub.refreshes(sid)) == 1
    assert stub.superseded_uses() == []
    assert session_count(pg) == 1


def test_k04_two_sessions_refresh_independently(pg: Postgres, stub: oidc_stub.Stub) -> None:
    with backends(pg, stub) as (a, b):
        stub.access_lifespan_seconds = 1
        first, second = login(a), login(b)
        stub.access_lifespan_seconds = 240
        time.sleep(1.3)
        stub.refresh_delay_seconds = 2.0
        started = time.monotonic()
        outcomes = concurrently([lambda: send(a, first), lambda: send(b, second)])
        elapsed = time.monotonic() - started
    assert [o.status for o in outcomes] == [200, 200]
    assert elapsed < 3.5, elapsed
    assert len(stub.refreshes()) == 2
    assert {c.sid for c in stub.refreshes()} == set(stub.sessions)
