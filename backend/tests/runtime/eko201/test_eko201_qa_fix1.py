"""EKO-2-01 QA contrasts for fix round 1: mechanisms the fix added that its own carriers cannot
tell apart from their neighbours.

- R-01 lock-free cached lookup: a token whose key is cached is served while another key
  identifier's fetch is in flight in the same process.
- R-03 storage failure at the callback: the callback's database read failing sends the browser
  to the failure page like any other unavailable callback.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import AppFactory, session_count, set_cookies
from tests.runtime.eko201.processes import Backend, backend, login
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

FAILURE_PAGE = "/logowanie-nieudane"
REFETCH_SECONDS = 10.0


def _timed(target: Backend, session: str) -> tuple[int | None, float]:
    started = time.monotonic()
    try:
        status: int | None = target.get("/api/auth/session", session, timeout=60).status_code
    except httpx.HTTPError:
        status = None
    return status, time.monotonic() - started


def _wait_until(condition: Callable[[], bool], seconds: float = 15) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def _in_background(target: Backend, session: str) -> list[tuple[int | None, float]]:
    found: list[tuple[int | None, float]] = []
    threading.Thread(target=lambda: found.append(_timed(target, session)), daemon=True).start()
    return found


# R-01 ---------------------------------------------------------------------------------------


def test_qa_r01_a_cached_key_is_served_while_another_key_fetch_is_in_flight(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    with backend(pg, stub) as warm:
        first = login(warm)
        cached_at = time.monotonic()
        # A second session, signed under a new key identifier, made by another process.
        stub.kid = "stub-key-2"
        stub.published = [
            oidc_stub.public_jwk(stub.signing_key, "stub-key-1"),
            oidc_stub.public_jwk(stub.signing_key, "stub-key-2"),
        ]
        with backend(pg, stub) as other:
            second = login(other)
        time.sleep(max(0.0, REFETCH_SECONDS + 0.5 - (time.monotonic() - cached_at)))
        stub.certs_mode = "hang"
        before = stub.certs_calls
        pending = _in_background(warm, second)
        _wait_until(lambda: stub.certs_calls > before)
        status, seconds = _timed(warm, first)
        _wait_until(lambda: bool(pending), seconds=30)
        stub.release.set()
    assert (status, seconds < 1.0) == (200, True), (status, seconds)
    # Contrast: the request whose key was unknown did wait for the fetch and was refused service.
    [(unknown_status, unknown_seconds)] = pending
    assert unknown_status == 503 and unknown_seconds >= 1.0, pending


# R-03 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("storage_fails", [True, False], ids=["storage-fails", "contrast"])
def test_qa_r03_storage_failure_at_the_callback_redirects_to_the_failure_page(
    make_app: AppFactory,
    browser_for: Any,
    pg: Postgres,
    monkeypatch: pytest.MonkeyPatch,
    storage_fails: bool,
) -> None:
    from app.data.sessions import StorageUnavailable

    app = make_app()
    browser = browser_for(app)
    path = browser.at_identity_server(browser.start_login("/klienci"))
    if storage_fails:

        def unreachable(transaction_hash: str) -> None:
            raise StorageUnavailable

        monkeypatch.setattr(app.state.auth.store, "take_transaction", unreachable)
    answer = browser.send("GET", path)
    expected = FAILURE_PAGE if storage_fails else "/klienci"
    assert (answer.status_code, answer.headers.get("location")) == (303, expected), answer.text
    names = {cookie.name for cookie in set_cookies(answer)}
    assert ("__Host-eko_session" in names) == (not storage_fails)
    assert session_count(pg) == (0 if storage_fails else 1)
