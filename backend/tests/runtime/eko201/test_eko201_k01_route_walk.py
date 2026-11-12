"""EKO-2-01 K-01 (ADR-0003-C4, C23 exemption half): every API operation outside the explicit
exemption list answers 401 without a valid session and its authenticated result with one.

Walks the route table of the shipped `create_app()` as served (included routers flattened). The
token variants are made without planting rows: a session is created through the real login flow
against the stub, and the verifying side is changed by exactly one element (published key,
expected issuer, expected audience, refresh outcome).
"""

from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from tests.runtime.eko201.conftest import (
    AppFactory,
    Browser,
    FakeClock,
    session_count,
)
from tests.support import oidc_stub
from tests.support.api_surface import route_contexts
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

# The test's own exemption list (ADR-0003 addendum of 2026-10-28): exactly these three routes.
EXEMPT = frozenset({"/api/auth/login", "/api/auth/callback", "/api/health"})
# The protected operations this Story adds; the walk must reach them.
PROTECTED = {("GET", "/api/auth/session"), ("POST", "/api/auth/logout")}
EXPIRED = {"seconds": 241}


class Probe(BaseModel):
    reached: bool


def operations(app: FastAPI) -> list[tuple[str, str]]:
    found = []
    for context in route_contexts(app):
        path = context.path or ""
        for method in sorted(getattr(context.route, "methods", None) or set()):
            if path.startswith("/api"):
                found.append((method, path))
    return found


def protected_operations(app: FastAPI) -> list[tuple[str, str]]:
    return [(m, p) for m, p in operations(app) if p not in EXEMPT]


def call(browser: Browser, method: str, path: str) -> int:
    return browser.send(method, path).status_code


def test_k01_route_walk_without_a_session_answers_401_outside_exactly_three_routes(
    make_app: AppFactory, browser_for: Any
) -> None:
    app = make_app()
    walked = operations(app)
    assert PROTECTED <= set(walked), walked
    browser = browser_for(app)
    answered = {(m, p): call(browser, m, p) for m, p in walked}
    not_401 = {p for (m, p), status in answered.items() if status != 401}
    assert not_401 == set(EXEMPT), answered


def test_k01_exemption_list_held_by_the_access_dependency_is_exactly_three() -> None:
    from app import main

    assert main.PUBLIC_PATHS == EXEMPT


def test_k01_a_newly_registered_route_outside_the_list_is_protected(
    make_app: AppFactory, browser_for: Any
) -> None:
    app = make_app()

    @app.post("/api/eko201-probe")
    def probe() -> Probe:
        return Probe(reached=True)

    browser = browser_for(app)
    assert browser.send("POST", "/api/eko201-probe").status_code == 401
    browser.login()
    reached = browser.send("POST", "/api/eko201-probe")
    assert reached.status_code == 200, reached.text
    assert reached.json() == {"reached": True}


@pytest.mark.parametrize(
    "cookie",
    ["", "x", "not a token", "A" * 42, "A" * 44, "A" * 43, "A" * 5000, "../../etc", "A" * 42 + "%"],
    ids=["empty", "short", "spaces", "42", "44", "unknown", "very-long", "path", "bad-character"],
)
def test_k01_missing_empty_malformed_or_unknown_session_cookie_answers_401(
    make_app: AppFactory, browser_for: Any, cookie: str
) -> None:
    browser = browser_for(make_app())
    browser.jar["__Host-eko_session"] = cookie
    for method, path in PROTECTED:
        assert call(browser, method, path) == 401


def test_k01_valid_session_reaches_the_authenticated_result(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    browser = browser_for(make_app())
    assert call(browser, "GET", "/api/auth/session") == 401
    browser.login()
    answer = browser.send("GET", "/api/auth/session")
    assert answer.status_code == 200, answer.text
    assert answer.json()["subject"] == stub.next_user.sub


def _logged_in(make_app: AppFactory, browser_for: Any) -> str:
    browser = browser_for(make_app())
    browser.login()
    assert browser.session is not None
    return str(browser.session)


@pytest.mark.parametrize("variant", ["signature", "issuer", "audience"])
def test_k01_wrong_signature_issuer_or_audience_answers_401(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, variant: str
) -> None:
    session = _logged_in(make_app, browser_for)
    overrides: dict[str, str] = {}
    if variant == "signature":
        # Same key identifier, other key: the stored token's signature no longer verifies.
        stub.published = [oidc_stub.public_jwk(oidc_stub.new_key(), stub.kid)]
    elif variant == "issuer":
        overrides["APP_OIDC_ISSUER"] = stub.issuer.replace("/realms/eko", "/realms/other")
        overrides["APP_OIDC_INTERNAL_URL"] = stub.issuer
    else:
        overrides["APP_OIDC_CLIENT_ID"] = "other-client"
    verifier = browser_for(make_app(**overrides))
    verifier.jar["__Host-eko_session"] = session
    assert call(verifier, "GET", "/api/auth/session") == 401
    # Contrast: the same session, verified as configured, is accepted.
    if variant == "signature":
        stub.published = [oidc_stub.public_jwk(stub.signing_key, stub.kid)]
    accepted = browser_for(make_app())
    accepted.jar["__Host-eko_session"] = session
    assert call(accepted, "GET", "/api/auth/session") == 200


def test_k01_expired_token_refused_refresh_answers_401_and_deletes_the_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    browser.login()
    clock.advance(**EXPIRED)
    stub.refresh_mode = "refuse"
    assert call(browser, "GET", "/api/auth/session") == 401
    assert session_count(pg) == 0
    assert len(stub.refreshes()) == 1


def test_k01_expired_token_unreachable_identity_server_answers_503_and_keeps_the_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    browser.login()
    clock.advance(**EXPIRED)
    stub.refresh_mode = "error"
    assert call(browser, "GET", "/api/auth/session") == 503
    assert session_count(pg) == 1
    # Contrast: a later request, with the identity server answering, refreshes and is served.
    stub.refresh_mode = "answer"
    assert call(browser, "GET", "/api/auth/session") == 200
    assert session_count(pg) == 1


def test_k01_expired_token_with_no_listener_answers_503_and_keeps_the_session(
    make_app: AppFactory, browser_for: Any, clock: FakeClock, pg: Postgres
) -> None:
    from tests.unit.conftest import closed_local_port

    session = _logged_in(make_app, browser_for)
    clock.advance(**EXPIRED)
    down = browser_for(make_app(APP_OIDC_INTERNAL_URL=f"http://127.0.0.1:{closed_local_port()}"))
    down.jar["__Host-eko_session"] = session
    assert call(down, "GET", "/api/auth/session") == 503
    assert session_count(pg) == 1


def test_k01_expired_token_is_never_served_unrefreshed(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock
) -> None:
    browser = browser_for(make_app())
    browser.login()
    clock.advance(seconds=239)
    assert call(browser, "GET", "/api/auth/session") == 200
    assert stub.refreshes() == []
    clock.advance(seconds=1)
    assert call(browser, "GET", "/api/auth/session") == 200
    assert len(stub.refreshes()) == 1


SCENARIOS = ("none", "signature", "refused", "unreachable", "valid")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_k01_every_protected_operation_answers_per_session_state(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    scenario: str,
) -> None:
    """ADR-0003-C4: the walk, one session state at a time, over every protected operation."""
    expected = {"none": 401, "signature": 401, "refused": 401, "unreachable": 503}
    walked = protected_operations(make_app())
    assert PROTECTED <= set(walked), walked
    for method, path in walked:
        stub.refresh_mode = "answer"
        stub.published = [oidc_stub.public_jwk(stub.signing_key, stub.kid)]
        browser = browser_for(make_app())
        if scenario != "none":
            browser.login()
        before = session_count(pg)
        if scenario == "signature":
            stub.published = [oidc_stub.public_jwk(oidc_stub.new_key(), stub.kid)]
            browser = Browser(browser_for(make_app()).client, dict(browser.jar))
        elif scenario in {"refused", "unreachable"}:
            clock.advance(**EXPIRED)
            stub.refresh_mode = "refuse" if scenario == "refused" else "error"
        status = call(browser, method, path)
        if scenario == "valid":
            assert status not in {401, 403, 404, 405, 503}, (method, path, status)
            assert status < 400, (method, path, status)
        else:
            assert status == expected[scenario], (method, path, status)
        if scenario == "refused":
            assert session_count(pg) == before - 1, (method, path)
        if scenario == "unreachable":
            assert session_count(pg) == before, (method, path)


def test_k01_health_stays_public_and_status_only(
    make_app: AppFactory, browser_for: Any
) -> None:
    browser = browser_for(make_app())
    got = browser.send("GET", "/api/health")
    assert (got.status_code, got.json()) == (200, {"status": "ok"})
    assert browser.send("HEAD", "/api/health").status_code == 200
    assert browser.send("POST", "/api/health").status_code == 405
