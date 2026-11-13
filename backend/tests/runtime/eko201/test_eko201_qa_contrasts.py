"""EKO-2-01 QA contrasts: scenarios the producer carriers left to a mechanism they did not isolate.

- K-02: the refresh token is a JWT in Keycloak, and it is the one token only
  `carries_forbidden_claim` inspects; and a refreshed ID token is inspected only by the same
  check in the refresh path, never by access-token verification.
- K-05: the holder's death observed by behaviour alone, with no `pg_locks` read, so a lock that
  outlives its holder fails on continued exclusion rather than on a lock-table observation.
- K-04 / ADR-0003-C18: the five-second waiter bound on its own, with a holder that never finishes
  (its lock held by a connection that does not die), so the holder's call timeout cannot be what
  ends the wait.
"""

import contextlib
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import AppFactory, FakeClock, session_count
from tests.runtime.eko201.processes import Backend, backend, backends, login
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

EXPIRED = {"seconds": 241}
ABSOLUTE = timedelta(hours=10)
FORBIDDEN = ("email", "preferred_username")
BOUND = 6.0
# Death of the holder is noticed by PostgreSQL when its connection closes; a later request may
# still meet the lock once and wait out its own bound. Two waiter bounds plus slack.
RECOVERY_SECONDS = 15.0


# K-01 -----------------------------------------------------------------------------------------
# The producer's audience variant changes the expected client id, which also trips the `azp`
# comparison; here `azp` stays the backend's own client and only `aud` names another one.


@pytest.mark.parametrize("audience", ["own", "other"])
@pytest.mark.parametrize("where", ["access", "id"])
def test_qa_k01_login_token_whose_only_defect_is_its_audience_is_refused(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    pg: Postgres,
    where: str,
    audience: str,
) -> None:
    if audience == "other":
        overrides = stub.access_overrides if where == "access" else stub.id_overrides
        overrides["aud"] = ["other-client"] if where == "access" else "other-client"
    answer = browser_for(make_app()).login()
    if audience == "own":
        assert answer.status_code == 303, answer.text
        assert session_count(pg) == 1
    else:
        assert answer.status_code == 400, answer.text
        assert session_count(pg) == 0


@pytest.mark.parametrize("audience", ["own", "other"])
def test_qa_k01_refreshed_access_token_for_another_audience_ends_the_session(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    audience: str,
) -> None:
    browser = browser_for(make_app())
    assert browser.login().status_code == 303
    clock.advance(**EXPIRED)
    if audience == "other":
        stub.access_overrides["aud"] = ["other-client"]
    status = browser.send("GET", "/api/auth/session").status_code
    assert len(stub.refreshes()) == 1
    assert (status, session_count(pg)) == ((200, 1) if audience == "own" else (401, 0))


# K-02 -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("claim", [None, *FORBIDDEN], ids=["contrast", *FORBIDDEN])
def test_qa_k02_refresh_token_carrying_email_or_username_is_not_stored(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres, claim: str | None
) -> None:
    # Both cases issue a JWT refresh token; only the forbidden claim's presence differs.
    stub.refresh_overrides = {"scope": "openid"}
    if claim is not None:
        stub.refresh_overrides[claim] = "synthetic.rep@example.invalid"
    browser = browser_for(make_app())
    answer = browser.login()
    if claim is None:
        assert answer.status_code == 303, answer.text
        assert session_count(pg) == 1
    else:
        assert answer.status_code == 400, answer.text
        assert session_count(pg) == 0


@pytest.mark.parametrize("claim", [None, *FORBIDDEN], ids=["contrast", *FORBIDDEN])
def test_qa_k02_refreshed_id_token_carrying_email_or_username_ends_the_session(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    claim: str | None,
) -> None:
    browser = browser_for(make_app())
    assert browser.login().status_code == 303
    clock.advance(**EXPIRED)
    if claim is not None:
        stub.id_overrides[claim] = "synthetic.rep@example.invalid"
    status = browser.send("GET", "/api/auth/session").status_code
    assert len(stub.refreshes()) == 1
    if claim is None:
        assert status == 200
        assert session_count(pg) == 1
    else:
        assert status == 401
        assert session_count(pg) == 0


# K-06 -----------------------------------------------------------------------------------------


def _sweep_at(clock: FakeClock, pg: Postgres, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import Settings, load_settings
    from app.data.database import Database
    from app.services.retention import sweep

    with monkeypatch.context() as scoped:
        for name, value in pg.app_env().items():
            scoped.setenv(name, value)
        database = Database.from_settings(load_settings(Settings))
    try:
        sweep(database, clock.now())
    finally:
        database.dispose()


USED_FOR = [None, timedelta(hours=9)]


@pytest.mark.parametrize("used_for", USED_FOR, ids=["never-used", "used-until-9h"])
def test_qa_k06_retention_counts_from_creation_even_for_a_session_used_before_abandonment(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    monkeypatch: pytest.MonkeyPatch,
    used_for: timedelta | None,
) -> None:
    # Retention's bound is creation + 10 h (ADR-0005-C8), not last use + 10 h: a session active
    # until 9 h and then abandoned holds its encrypted tokens no longer than one never used.
    stub.access_lifespan_seconds = 36000 * 2
    created = clock.at
    browser = browser_for(make_app())
    browser.login()
    if used_for is not None:
        while clock.at + timedelta(minutes=20) <= created + used_for:
            clock.advance(minutes=20)
            assert browser.send("GET", "/api/auth/session").status_code == 200
    clock.at = created + ABSOLUTE - timedelta(microseconds=1)
    _sweep_at(clock, pg, monkeypatch)
    assert session_count(pg) == 1
    clock.at = created + ABSOLUTE
    _sweep_at(clock, pg, monkeypatch)
    assert session_count(pg) == 0


# K-05 -----------------------------------------------------------------------------------------


def _expired(stub: oidc_stub.Stub, target: Backend) -> str:
    stub.access_lifespan_seconds = 1
    session = login(target)
    stub.access_lifespan_seconds = 240
    time.sleep(1.3)
    return session


def _quiet(target: Backend, session: str) -> None:
    with contextlib.suppress(httpx.HTTPError):
        target.get("/api/auth/session", session, timeout=60)


def _wait_until(condition: Callable[[], bool], seconds: float = 15) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def test_qa_k05_holder_death_is_followed_by_service_without_reading_the_lock_table(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    with backend(pg, stub) as survivor, backend(pg, stub) as holder:
        session = _expired(stub, survivor)
        stub.refresh_mode = "hang"
        threading.Thread(target=lambda: _quiet(holder, session), daemon=True).start()
        _wait_until(lambda: len(stub.refreshes()) == 1)
        holder.kill()
        stub.refresh_mode = "answer"
        stub.release.set()
        killed = time.monotonic()
        statuses: list[int] = []
        while time.monotonic() - killed < RECOVERY_SECONDS:
            statuses.append(survivor.get("/api/auth/session", session).status_code)
            if statuses[-1] == 200:
                break
        recovered = time.monotonic() - killed
        later = [survivor.get("/api/auth/session", session).status_code for _ in range(3)]
    assert statuses[-1] == 200, (statuses, round(recovered, 2))
    assert set(statuses[:-1]) <= {503}, statuses
    assert later == [200, 200, 200]
    assert session_count(pg) == 1
    assert len(stub.refreshes()) == 2


# K-04 -----------------------------------------------------------------------------------------


def _timed(target: Backend, session: str) -> tuple[int | None, float]:
    started = time.monotonic()
    try:
        status: int | None = target.get("/api/auth/session", session, timeout=40).status_code
    except httpx.TimeoutException:
        status = None
    return status, time.monotonic() - started


def test_qa_k04_waiter_whose_holder_dies_answers_503_in_time_without_refreshing(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    # In the hanging carrier a waiter's own bound ends before the holder's call timeout frees the
    # lock, so the waiter never sees a free lock there. Here the holder dies mid-wait while
    # Keycloak still hangs: the waiter sees the lock free and must answer 503 without a refresh
    # of its own (ADR-0002-C16 "no waiter refreshes"; ADR-0003-C28 bounds still apply).
    with backend(pg, stub) as waiter_side, backend(pg, stub) as holder:
        session = _expired(stub, waiter_side)
        stub.refresh_mode = "hang"
        threading.Thread(target=lambda: _quiet(holder, session), daemon=True).start()
        _wait_until(lambda: len(stub.refreshes()) == 1)
        outcome: list[tuple[int | None, float]] = []
        waiter = threading.Thread(target=lambda: outcome.append(_timed(waiter_side, session)))
        waiter.start()
        time.sleep(1.0)
        holder.kill()
        waiter.join(timeout=60)
        refreshes = len(stub.refreshes())
        stub.release.set()
    [(status, seconds)] = outcome
    assert (status, refreshes) == (503, 1), (status, round(seconds, 2), refreshes)
    assert seconds < BOUND, seconds
    assert session_count(pg) == 1


def test_qa_k04_waiter_bound_ends_the_wait_when_the_holder_never_finishes(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    from app.data.sessions import REFRESH_LOCK_CLASS, lock_key

    with backends(pg, stub) as (a, b):
        session = _expired(stub, a)
        [[row_id]] = pg.rows("SELECT id FROM app_session")
        with pg.connect() as stranded:
            # A holder that never finishes and never dies: its lock outlives every call timeout.
            stranded.execute(
                "SELECT pg_advisory_lock(%s::integer, %s::integer)",
                (REFRESH_LOCK_CLASS, lock_key(int(row_id))),
            )
            with ThreadPoolExecutor(max_workers=4) as pool:
                outcomes = list(pool.map(lambda call: call(), [
                    partial(_timed, t, session) for t in (a, b, a, b)
                ]))  # fmt: skip
    assert [status for status, _ in outcomes] == [503] * 4, outcomes
    assert max(seconds for _, seconds in outcomes) < BOUND, outcomes
    assert stub.refreshes() == []
    assert session_count(pg) == 1
