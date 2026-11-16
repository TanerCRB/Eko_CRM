"""EKO-2-01 fix round 1 (#21): Reviewer R-01, R-02, R-03 (backend half), R-04, R-06 and Security
Auditor B-01, each with the contrast that shows the test reads the behaviour it names.

All against real PostgreSQL and the OIDC stub; R-01 uses fresh uvicorn processes, so the key
cache is cold exactly as after a deploy.
"""

import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import (
    LOGIN_COOKIE,
    SESSION_COOKIE,
    AppFactory,
    FakeClock,
    session_count,
    set_cookies,
    transaction_count,
)
from tests.runtime.eko201.processes import Backend, backend, login
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

EXPIRED = {"seconds": 241}
FAILURE_PAGE = "/logowanie-nieudane"
# The cap chosen for B-01 (app.domain.session_policy.OPEN_LOGIN_TRANSACTION_LIMIT).
CAP = 1000
BOUND = 6.0


def _code_warnings(caplog: pytest.LogCaptureFixture, code: str) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name.startswith("app.") and code in r.getMessage()
    ]


# R-01 — the cold key cache ------------------------------------------------------------------


def _timed(target: Backend, session: str) -> tuple[int | None, float]:
    started = time.monotonic()
    try:
        status: int | None = target.get("/api/auth/session", session, timeout=40).status_code
    except httpx.TimeoutException:
        status = None
    return status, time.monotonic() - started


@pytest.fixture
def warm_session(pg: Postgres, stub: oidc_stub.Stub) -> Iterator[tuple[Backend, str]]:
    with backend(pg, stub) as warm:
        session = login(warm)
        assert warm.get("/api/auth/session", session).status_code == 200
        yield warm, session


def test_fix1_r01_cold_key_cache_with_hanging_keys_answers_every_request_503_in_time(
    pg: Postgres, stub: oidc_stub.Stub, warm_session: tuple[Backend, str]
) -> None:
    warm, session = warm_session
    stub.certs_mode = "hang"
    with backend(pg, stub) as cold:
        fetches_before = stub.certs_calls
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(lambda _: _timed(cold, session), range(10)))
        assert [status for status, _ in outcomes] == [503] * 10, outcomes
        assert max(seconds for _, seconds in outcomes) < BOUND, outcomes
        # One fetch in flight for all ten, and its failure is remembered for the refetch interval.
        assert stub.certs_calls - fetches_before == 1
        status, seconds = _timed(cold, session)
        assert (status, stub.certs_calls - fetches_before) == (503, 1)
        assert seconds < 1.0, seconds
        # Contrast: the process whose keys are cached keeps serving during the same hang.
        assert warm.get("/api/auth/session", session).status_code == 200
    stub.release.set()


# R-02 — only invalid_grant is a refusal ---------------------------------------------------


CLIENT_FAULTS = ["invalid_client", "unauthorized_client", "temporarily_unavailable"]


@pytest.mark.parametrize("code", CLIENT_FAULTS)
def test_fix1_r02_refresh_failing_on_a_client_fault_answers_503_and_keeps_the_session(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    caplog: pytest.LogCaptureFixture,
    code: str,
) -> None:
    browser = browser_for(make_app())
    browser.login()
    clock.advance(**EXPIRED)
    stub.refresh_mode, stub.refusal_code = "refuse", code
    with caplog.at_level(logging.WARNING):
        assert browser.send("GET", "/api/auth/session").status_code == 503
    assert session_count(pg) == 1
    assert _code_warnings(caplog, code), caplog.records
    # Contrast: invalid_grant is the user's session refused: 401 and the session deleted.
    stub.refusal_code = "invalid_grant"
    assert browser.send("GET", "/api/auth/session").status_code == 401
    assert session_count(pg) == 0


@pytest.mark.parametrize("code", CLIENT_FAULTS)
def test_fix1_r02_logout_failing_on_a_client_fault_answers_503_and_keeps_both_sessions(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    pg: Postgres,
    caplog: pytest.LogCaptureFixture,
    code: str,
) -> None:
    browser = browser_for(make_app())
    browser.login()
    [sid] = list(stub.sessions)
    stub.logout_mode, stub.refusal_code = "refuse", code
    with caplog.at_level(logging.WARNING):
        assert browser.send("POST", "/api/auth/logout").status_code == 503
    assert session_count(pg) == 1
    assert stub.sso_alive(sid)
    assert _code_warnings(caplog, code), caplog.records
    # Contrast: invalid_grant means Keycloak's session is already gone, so logout completes.
    stub.refusal_code = "invalid_grant"
    assert browser.send("POST", "/api/auth/logout").status_code == 200
    assert session_count(pg) == 0


@pytest.mark.parametrize("code", ["invalid_client", "invalid_grant"])
def test_fix1_r02_login_with_a_client_fault_is_unavailable_not_refused(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    pg: Postgres,
    caplog: pytest.LogCaptureFixture,
    code: str,
) -> None:
    stub.code_mode, stub.refusal_code = "refuse", code
    browser = browser_for(make_app())
    with caplog.at_level(logging.WARNING):
        answer = browser.login()
    assert (answer.status_code, answer.headers.get("location")) == (303, FAILURE_PAGE)
    assert session_count(pg) == 0
    # The backend's own fault is named in a warning; a refused code (the contrast) is not one.
    assert bool(_code_warnings(caplog, code)) == (code == "invalid_client"), caplog.records


# R-03 — the callback never leaves the browser on a JSON page -------------------------------


def _assert_failure_redirect(answer: httpx.Response, pg: Postgres) -> None:
    assert answer.status_code == 303, answer.text
    assert answer.headers["location"] == FAILURE_PAGE
    assert answer.json() == {"location": FAILURE_PAGE}
    cookies = {c.name: c for c in set_cookies(answer)}
    assert SESSION_COOKIE not in cookies
    assert cookies[LOGIN_COOKIE].cleared
    assert session_count(pg) == 0
    assert transaction_count(pg) == 0


def test_fix1_r03_refused_callback_redirects_to_the_failure_page(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    path = browser.at_identity_server(browser.start_login())
    _assert_failure_redirect(browser.send("GET", path.replace("state=", "state=x")), pg)


def test_fix1_r03_unavailable_callback_redirects_to_the_failure_page(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    stub.code_mode = "error"
    browser = browser_for(make_app())
    _assert_failure_redirect(browser.login(), pg)
    # Contrast: the same login with Keycloak answering creates the session and goes to the page.
    stub.code_mode = "answer"
    assert browser.login().headers["location"] == "/"
    assert session_count(pg) == 1


# R-04 — a failing probe never keeps the lock -----------------------------------------------


def _refresh_locks(pg: Postgres) -> list[tuple[Any, ...]]:
    from app.data.sessions import REFRESH_LOCK_CLASS

    return pg.rows(
        "SELECT objid FROM pg_locks WHERE locktype = 'advisory' AND objsubid = 2 AND granted "
        "AND classid = %s",
        (REFRESH_LOCK_CLASS,),
    )


@pytest.mark.parametrize("read_fails", [True, False], ids=["read-fails", "contrast"])
def test_fix1_r04_probe_whose_read_fails_leaves_no_refresh_lock(
    make_app: AppFactory,
    browser_for: Any,
    pg: Postgres,
    monkeypatch: pytest.MonkeyPatch,
    read_fails: bool,
) -> None:
    from sqlalchemy import text

    from app.data import sessions as data_sessions

    app = make_app()
    browser_for(app).login()
    [[session_id]] = pg.rows("SELECT id FROM app_session")
    store = app.state.auth.store
    if read_fails:

        def failing(connection: Any, where: Any) -> None:
            connection.execute(text("SELECT 1 / 0"))  # a statement error, not a disconnect

        monkeypatch.setattr(data_sessions, "_session", failing)
        with pytest.raises(data_sessions.StorageUnavailable):
            store.probe(int(session_id))
    else:
        assert store.probe(int(session_id)).lock_free
    assert _refresh_locks(pg) == []
    # The query sees a held lock: a holder's lock is listed while it is held.
    with store.refresh_holder(int(session_id)) as holder:
        assert holder is not None
        assert len(_refresh_locks(pg)) == 1


# R-06 — return_to is printable ASCII ------------------------------------------------------


@pytest.mark.parametrize(
    ("return_to", "location"),
    [("/klienci?q=ż", "/"), ("/klienci?q=é", "/"), ("/klienci?q=abc", "/klienci?q=abc")],
    ids=["non-latin-1", "latin-1", "ascii-contrast"],
)
def test_fix1_r06_non_ascii_return_to_falls_back_to_root_and_login_completes(
    make_app: AppFactory, browser_for: Any, pg: Postgres, return_to: str, location: str
) -> None:
    browser = browser_for(make_app())
    answer = browser.login(return_to)
    assert (answer.status_code, answer.headers["location"]) == (303, location), answer.text
    assert session_count(pg) == 1
    assert browser.session is not None


# B-01 — open login transactions are capped -------------------------------------------------


def _plant_transactions(pg: Postgres, count: int, created_at: datetime) -> None:
    pg.rows(
        "INSERT INTO login_transaction "
        "(transaction_hash, state_hash, nonce_hash, verifier, return_to, created_at) "
        "SELECT 'planted-' || g, 's', 'n', '\\x00'::bytea, '/', %s "
        "FROM generate_series(1, %s) AS g RETURNING 1",
        (created_at, count),
    )


def test_fix1_b01_the_cap_is_the_named_policy_value() -> None:
    from app.domain import session_policy

    assert session_policy.OPEN_LOGIN_TRANSACTION_LIMIT == CAP


@pytest.mark.parametrize(("planted", "accepted"), [(CAP - 1, True), (CAP, False), (CAP + 1, False)])
def test_fix1_b01_login_start_beyond_the_open_transaction_cap_answers_503(
    make_app: AppFactory,
    browser_for: Any,
    clock: FakeClock,
    pg: Postgres,
    planted: int,
    accepted: bool,
) -> None:
    _plant_transactions(pg, planted, clock.now() - timedelta(minutes=1))
    answer = browser_for(make_app()).start_login()
    if accepted:
        assert answer.status_code == 303, answer.text
        assert transaction_count(pg) == planted + 1
    else:
        assert answer.status_code == 503, answer.text
        assert answer.json() == {"detail": "temporarily unavailable"}
        assert set_cookies(answer) == []
        assert transaction_count(pg) == planted


def test_fix1_b01_expired_transactions_do_not_count_against_the_cap(
    make_app: AppFactory, browser_for: Any, clock: FakeClock, pg: Postgres
) -> None:
    _plant_transactions(pg, CAP, clock.now() - timedelta(minutes=10))
    assert browser_for(make_app()).start_login().status_code == 303
    assert transaction_count(pg) == CAP + 1
