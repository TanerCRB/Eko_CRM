"""EKO-2-02 K-01, the B-01 API half (ADR-0003 roles addendum of EKO-2-02, accepted 2026-11-16): a
session whose verified token holds no application role can still be ended. `POST /api/auth/logout`
is the one role-free operation; it keeps the `Origin` rule, still needs a session, and answers 503
with the session kept while the identity server cannot end its own session. Everything else stays
403 to that session, the session read included, and the role-free admission is one route object,
not a path: a route planted on the logout path with another method is CRM class.

Real PostgreSQL, the local OIDC stub and the shipped `create_app()` (EKO-2-01's carriers).
"""

from typing import Any

import pytest
from fastapi import FastAPI

from tests.runtime.eko201 import conftest as eko201
from tests.runtime.eko201.conftest import AppFactory, Browser, session_count
from tests.support import eko202_probe as probe
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

# EKO-2-01's carrier fixtures, bound here by name because they live in a sibling conftest.
pg = eko201.pg
clean = eko201.clean
stub = eko201.stub
clock = eko201.clock
make_app = eko201.make_app
browser_for = eko201.browser_for

LOGOUT = "/api/auth/logout"
SESSION = "/api/auth/session"
FOREIGN = "https://evil.test"


def role_less(app: FastAPI, browser_for: Any, stub: oidc_stub.Stub) -> Browser:
    stub.access_overrides = probe.role_claims()
    browser: Browser = browser_for(app)
    browser.login()
    assert browser.session is not None
    return browser


def test_k01_role_less_session_logs_out_and_ends_both_sessions(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser = role_less(make_app(), browser_for, stub)
    [sid] = stub.sessions
    assert session_count(pg) == 1
    answer = browser.send("POST", LOGOUT)
    assert (answer.status_code, answer.json()) == (200, {"status": "logged_out"})
    assert session_count(pg) == 0
    assert browser.session is None, "the session cookie was not cleared"
    assert len(stub.logout_calls) == 1
    assert not stub.sso_alive(sid), "end_session was not sent"


def test_k01_replayed_cookie_after_role_less_logout_is_401(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    browser = role_less(make_app(), browser_for, stub)
    cookie = str(browser.session)
    assert browser.send("POST", LOGOUT).status_code == 200
    browser.jar[eko201.SESSION_COOKIE] = cookie
    assert browser.send("POST", LOGOUT).status_code == 401
    browser.jar[eko201.SESSION_COOKIE] = cookie
    assert browser.send("GET", SESSION).status_code == 401
    assert len(stub.logout_calls) == 1


def test_k01_contrast_role_less_session_read_and_probe_answer_403(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    app = make_app()
    recorder = probe.install_probe(app)
    browser = role_less(app, browser_for, stub)
    assert browser.send("GET", SESSION).status_code == 403
    for method, path in sorted(probe.OPERATIONS):
        assert browser.send(method, path).status_code == 403, (method, path)
    assert recorder.received == []
    # The refusals end nothing; the same session is then ended by logout.
    assert session_count(pg) == 1
    assert browser.send("POST", LOGOUT).status_code == 200
    assert session_count(pg) == 0


def test_k01_role_less_logout_with_a_foreign_origin_is_403_and_keeps_the_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser = role_less(make_app(), browser_for, stub)
    for origin in (FOREIGN, None):
        refused = browser.send("POST", LOGOUT, origin=origin)
        assert refused.status_code == 403, origin
        assert refused.json() == {"detail": "origin refused"}
    assert session_count(pg) == 1
    assert stub.logout_calls == []
    assert browser.send("POST", LOGOUT).status_code == 200


def test_k01_role_less_logout_with_the_identity_server_unreachable_is_503_and_keeps_the_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser = role_less(make_app(), browser_for, stub)
    stub.logout_mode = "error"
    assert browser.send("POST", LOGOUT).status_code == 503
    assert session_count(pg) == 1
    assert browser.session is not None
    stub.logout_mode = "answer"
    assert browser.send("POST", LOGOUT).status_code == 200
    assert session_count(pg) == 0


@pytest.mark.parametrize("roles", [[], ["administrator"]], ids=["role-less", "administrator"])
def test_k01_a_route_planted_on_the_logout_path_with_another_method_is_not_role_free(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres, roles: list[str]
) -> None:
    app = make_app()

    @app.get(LOGOUT)
    def planted() -> dict[str, bool]:
        return {"reached": True}

    stub.access_overrides = probe.role_claims(client=roles)
    browser: Browser = browser_for(app)
    browser.login()
    assert browser.send("GET", LOGOUT).status_code == 403
    assert session_count(pg) == 1
    # Contrast: the listed operation on the same path is admitted.
    assert browser.send("POST", LOGOUT).status_code == 200
