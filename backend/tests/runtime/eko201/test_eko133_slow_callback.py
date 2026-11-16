"""EKO-1-33 K-01, K-02, K-05(b): a login whose callback verifies its tokens later than they expire.

The OIDC stub's answer to the code exchange is held back for a controlled interval after it mints
the tokens, so the interval from minting to the callback's verification is at least that long. The
access token's remaining life is measured at minting. Both backend processes run on the host's
real clock, as the EKO-2-01 cross-process carriers do.

Imports here are limited to names that exist at the pre-fix tree (4acdfd8), so restoring the
pre-fix harness files with `git show` leaves this file runnable (K-02 contrast).
"""

import time
import urllib.parse
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest

from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.runtime.eko201 import test_eko201_k05_holder_death as k05
from tests.runtime.eko201 import test_eko201_qa_contrasts as qa
from tests.runtime.eko201.conftest import SESSION_COOKIE, refused_at_callback, session_count
from tests.runtime.eko201.processes import Backend, backends
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

# Both intervals stay inside the 5-second read timeouts a login meets: the backend's on the exchange
# (`CALL_TIMEOUT_SECONDS`, app/auth/oidc.py) and the test client's on the callback (httpx's
# default, `processes.login`). A slower login ends as a timeout, not at the expiry check.
# K-01: longer than any life a 1-second token has left (at most 1 s).
REPRODUCTION_INTERVAL = 2.0
CONTRAST_LIFESPAN = 4
# K-02: the largest plausible interval on a shared runner. No CI timing of a login was observed
# (the backend's log goes to DEVNULL); 3.5 s is the 5-s timeout above less 1.5 s left for the
# backend's own work in the callback, including a fresh process's key-set fetch.
LARGEST_INTERVAL = 3.5
# Fraction of a second at which the token is minted: just after a whole second (about 1 s left on
# a 1-second token after truncation) and just before one (close to 0 s left).
AFTER_BOUNDARY = 0.02
BEFORE_BOUNDARY = 0.95


def slow_exchange(
    stub: oidc_stub.Stub,
    monkeypatch: pytest.MonkeyPatch,
    interval: float,
    at_fraction: float | None = None,
) -> list[float]:
    """Holds every code exchange's answer `interval` seconds after minting; returns the access
    token's remaining life at each minting, in seconds."""
    remaining: list[float] = []
    mint = stub.mint

    def held(user: oidc_stub.User, sid: str, nonce: str | None) -> dict[str, Any]:
        # A refresh mints without a nonce; only the login's exchange is held back.
        if nonce is None:
            return mint(user, sid, nonce)
        if at_fraction is not None:
            time.sleep((at_fraction - time.time() % 1) % 1)
        issued = mint(user, sid, nonce)
        claims = jwt.decode(issued["access_token"], options={"verify_signature": False})
        remaining.append(float(claims["exp"]) - time.time())
        time.sleep(interval)
        return issued

    monkeypatch.setattr(stub, "mint", held)
    return remaining


def callback(target: Backend) -> httpx.Response:
    """The login flow of `processes.login`, returning the callback's answer, not the cookie."""
    start = httpx.get(target.url + "/api/auth/login", follow_redirects=False)
    assert start.status_code == 303, start.text
    login_cookie = cookie_value(start, "__Host-eko_login")
    at_idp = httpx.get(start.headers["location"], follow_redirects=False)
    target_url = urllib.parse.urlsplit(at_idp.headers["location"])
    return httpx.get(
        f"{target.url}{target_url.path}?{target_url.query}",
        headers={"cookie": f"__Host-eko_login={login_cookie}"},
        follow_redirects=False,
        timeout=30,
    )


def cookie_value(response: httpx.Response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        key, _, value = header.split(";", 1)[0].partition("=")
        if key.strip() == name and value.strip():
            return value.strip()
    return None


def has_session_cookie(response: httpx.Response) -> bool:
    return cookie_value(response, SESSION_COOKIE) is not None


def code_exchanges(stub: oidc_stub.Stub) -> list[oidc_stub.TokenCall]:
    with stub.lock:
        return [c for c in stub.token_calls if c.grant_type == "authorization_code"]


@pytest.mark.parametrize(
    "at_fraction", [AFTER_BOUNDARY, BEFORE_BOUNDARY], ids=["after-boundary", "before-boundary"]
)
@pytest.mark.parametrize(
    "lifespan", [1, CONTRAST_LIFESPAN], ids=["one-second-token", "contrast-four-seconds"]
)
def test_eko133_k01_short_lived_login_is_refused_by_expiry_at_the_pre_fix_harness(
    pg: Postgres,
    stub: oidc_stub.Stub,
    monkeypatch: pytest.MonkeyPatch,
    lifespan: int,
    at_fraction: float,
) -> None:
    # A 1-second lifespan is the carriers' short-lived login at the pre-fix tree (4acdfd8).
    # Only the lifespan differs between the two cases: signature, issuer, audience, nonce, subject
    # and claims are the stub's defaults in both, so the contrast leaves expiry as the one cause.
    remaining = slow_exchange(stub, monkeypatch, REPRODUCTION_INTERVAL, at_fraction)
    with backends(pg, stub) as (a, b):
        stub.access_lifespan_seconds = lifespan
        # Each process's first login, so each verification includes the key-set fetch.
        answers = [callback(a), callback(b)]
    exchanges = code_exchanges(stub)
    assert len(remaining) == 2, remaining
    assert len(exchanges) == 2 and all(c.finished is not None for c in exchanges), exchanges
    if lifespan == 1:
        assert all(life < REPRODUCTION_INTERVAL for life in remaining), remaining
        assert all(refused_at_callback(answer) for answer in answers), answers
        assert not any(has_session_cookie(answer) for answer in answers)
        assert session_count(pg) == 0
    else:
        assert all(life > REPRODUCTION_INTERVAL for life in remaining), remaining
        assert all(answer.status_code == 303 for answer in answers), answers
        assert not any(refused_at_callback(answer) for answer in answers), answers
        assert all(has_session_cookie(answer) for answer in answers)
        assert session_count(pg) == 2


def _k04(stub: oidc_stub.Stub, a: Backend, b: Backend) -> list[str]:
    session, _ = k04.expired_session(stub, a)
    return [session]


def _two_in_a_row(stub: oidc_stub.Stub, a: Backend, b: Backend) -> list[str]:
    # The shape of `test_k04_two_sessions_refresh_independently`: one login per process.
    first, _ = k04.expired_session(stub, a)
    second, _ = k04.expired_session(stub, b)
    return [first, second]


CARRIER_LOGINS: dict[str, Callable[[oidc_stub.Stub, Backend, Backend], list[str]]] = {
    "k04-expired-session": _k04,
    "k04-two-logins-on-two-processes": _two_in_a_row,
    "k05-expired": lambda stub, a, b: [k05._expired(stub, a)],
    "qa-expired": lambda stub, a, b: [qa._expired(stub, a)],
}


@pytest.mark.parametrize("carrier", list(CARRIER_LOGINS))
def test_eko133_k02_short_lived_login_survives_a_slow_callback(
    pg: Postgres, stub: oidc_stub.Stub, monkeypatch: pytest.MonkeyPatch, carrier: str
) -> None:
    remaining = slow_exchange(stub, monkeypatch, LARGEST_INTERVAL)
    with backends(pg, stub) as (a, b):
        sessions = CARRIER_LOGINS[carrier](stub, a, b)
        targets = [a, b][: len(sessions)]
        first = [
            t.get("/api/auth/session", s).status_code
            for t, s in zip(targets, sessions, strict=True)
        ]
    assert all(life > LARGEST_INTERVAL for life in remaining), remaining
    # K-05(b): one exchange per login, so no retry stands behind a login that got through.
    assert len(code_exchanges(stub)) == len(sessions)
    assert session_count(pg) == len(sessions)
    # The carriers' premise: the first request finds the access token expired and refreshes.
    assert first == [200] * len(sessions), first
    assert len(stub.refreshes()) == len(sessions)
