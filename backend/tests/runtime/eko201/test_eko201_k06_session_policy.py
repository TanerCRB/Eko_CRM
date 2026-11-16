"""EKO-2-01 K-06, backend half (ADR-0003-C24 application half, C25 against the stub, ADR-0005-C8):
the 30-minute idle and 10-hour absolute limits on a controlled clock, logout ending both the
application session and the identity server's session, and retention of abandoned sessions and
login transactions.

The realm-export, MFA and running-Keycloak SSO halves are carried by developer-infrastructure.
"""

import threading
from datetime import timedelta
from typing import Any

import pytest

from tests.runtime.eko201.conftest import (
    AppFactory,
    FakeClock,
    session_count,
    transaction_count,
)
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

TICK = timedelta(microseconds=1)
IDLE = timedelta(minutes=30)
ABSOLUTE = timedelta(hours=10)
BOUNDARY = [(-TICK, True), (timedelta(0), False), (TICK, False)]


def _status(browser: Any) -> int:
    return int(browser.send("GET", "/api/auth/session").status_code)


@pytest.mark.parametrize(("offset", "accepted"), BOUNDARY)
def test_k06_idle_limit_is_thirty_minutes(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    offset: timedelta,
    accepted: bool,
) -> None:
    stub.access_lifespan_seconds = 36000 * 2
    browser = browser_for(make_app())
    browser.login()
    clock.at += IDLE + offset
    assert _status(browser) == (200 if accepted else 401)
    assert session_count(pg) == (1 if accepted else 0)


def test_k06_activity_extends_only_the_idle_deadline(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock, pg: Postgres
) -> None:
    stub.access_lifespan_seconds = 36000 * 2
    browser = browser_for(make_app())
    browser.login()
    created = clock.at
    # Activity every 29 minutes keeps the session past many idle periods.
    while clock.at + timedelta(minutes=29) < created + ABSOLUTE:
        clock.advance(minutes=29)
        assert _status(browser) == 200, clock.at - created
    # ... but never past the absolute maximum: just before it works, at it is refused.
    clock.at = created + ABSOLUTE - TICK
    assert _status(browser) == 200
    clock.at = created + ABSOLUTE
    assert _status(browser) == 401
    assert session_count(pg) == 0


@pytest.mark.parametrize(("offset", "accepted"), BOUNDARY)
def test_k06_absolute_limit_is_ten_hours(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    offset: timedelta,
    accepted: bool,
) -> None:
    stub.access_lifespan_seconds = 36000 * 2
    browser = browser_for(make_app())
    browser.login()
    created = clock.at
    # Activity under 30 minutes apart, so only the absolute limit can refuse.
    while clock.at + timedelta(minutes=20) < created + ABSOLUTE:
        clock.advance(minutes=20)
        assert _status(browser) == 200
    clock.at = created + ABSOLUTE + offset
    assert _status(browser) == (200 if accepted else 401)


def test_k06_logout_deletes_the_session_and_ends_the_identity_server_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    browser.login()
    old = browser.session
    [sid] = list(stub.sessions)
    # Contrast before logout: the cookie and the identity server's session both work.
    assert _status(browser) == 200
    assert stub.sso_alive(sid)
    answer = browser.send("POST", "/api/auth/logout")
    assert answer.status_code == 200, answer.text
    assert session_count(pg) == 0
    assert not stub.sso_alive(sid)
    assert len(stub.logout_calls) == 1
    browser.jar["__Host-eko_session"] = old
    assert _status(browser) == 401
    # Repeated logout with the old cookie: not authenticated.
    assert browser.send("POST", "/api/auth/logout").status_code == 401


def test_k06_logout_with_the_identity_server_unreachable_keeps_the_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    browser.login()
    stub.logout_mode = "error"
    assert browser.send("POST", "/api/auth/logout").status_code == 503
    assert session_count(pg) == 1
    stub.logout_mode = "answer"
    assert browser.send("POST", "/api/auth/logout").status_code == 200
    assert session_count(pg) == 0


def test_k06_logout_after_the_identity_server_session_already_ended_still_logs_out(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    browser.login()
    for session in stub.sessions.values():
        session.ended = True
    assert browser.send("POST", "/api/auth/logout").status_code == 200
    assert session_count(pg) == 0


def _sweep(clock: FakeClock, pg: Postgres, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_k06_abandoned_sessions_are_deleted_by_ten_hours_after_creation(
    make_app: AppFactory,
    browser_for: Any,
    clock: FakeClock,
    pg: Postgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = clock.at
    browser_for(make_app()).login()
    clock.advance(minutes=1)
    browser_for(make_app()).login()
    assert session_count(pg) == 2
    clock.at = created + ABSOLUTE - TICK
    _sweep(clock, pg, monkeypatch)
    assert session_count(pg) == 2
    clock.at = created + ABSOLUTE
    _sweep(clock, pg, monkeypatch)
    assert session_count(pg) == 1
    clock.at = created + ABSOLUTE + timedelta(minutes=1)
    _sweep(clock, pg, monkeypatch)
    assert session_count(pg) == 0
    assert pg.rows("SELECT count(*) FROM app_session WHERE tokens IS NOT NULL")[0][0] == 0


def test_k06_abandoned_login_transactions_are_deleted_by_one_hour_after_creation(
    make_app: AppFactory,
    browser_for: Any,
    clock: FakeClock,
    pg: Postgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = clock.at
    browser_for(make_app()).start_login()
    assert transaction_count(pg) == 1
    clock.at = created + timedelta(hours=1) - TICK
    _sweep(clock, pg, monkeypatch)
    assert transaction_count(pg) == 1
    clock.at = created + timedelta(hours=1)
    _sweep(clock, pg, monkeypatch)
    assert transaction_count(pg) == 0


def test_k06_the_worker_runs_the_retention_sweep(
    make_app: AppFactory,
    browser_for: Any,
    clock: FakeClock,
    pg: Postgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker

    browser_for(make_app()).login()
    browser_for(make_app()).start_login()
    clock.advance(hours=11)
    for name, value in pg.app_env(2, 0).items():
        monkeypatch.setenv(name, value)
    stop = threading.Event()
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(worker.run(stop, clock=clock)))
    thread.start()
    try:
        for _ in range(100):
            if session_count(pg) == 0 and transaction_count(pg) == 0:
                break
            threading.Event().wait(0.1)
        assert (session_count(pg), transaction_count(pg)) == (0, 0)
    finally:
        stop.set()
        thread.join(timeout=10)
    assert result == [0]
