"""EKO-2-02 QA contrasts for K-01 and K-02.

K-01: every probe route and every product route declares `current_caller` itself, so a role check
living only in `current_caller` (instead of in the application-wide dependency) would pass the
whole role walk. A route registered after `create_app()` with no dependency of its own reaches
only the application-wide dependency: a role-less session must get 403 there, and so must an
administrator-only session, because an unmarked route is CRM class by default (fix round 1,
R-01), where a `rep` session gets the handler's answer (one changed element: the token's role
set).

K-02: the walk injects `manager` into a `rep` session. A fallback that honours a client-sent role
only when the token holds none passes that walk; here a role-less session names `rep` in each
channel and must stay refused, where the token claim `rep` is served.
"""

from typing import Any

import pytest
from fastapi import FastAPI

from tests.runtime.eko201 import conftest as eko201
from tests.runtime.eko201.conftest import AppFactory, Browser
from tests.support import eko202_probe as probe
from tests.support import oidc_stub

pytestmark = pytest.mark.runtime

# EKO-2-01's carrier fixtures, bound here by name because they live in a sibling conftest.
pg = eko201.pg
clean = eko201.clean
stub = eko201.stub
clock = eko201.clock
make_app = eko201.make_app
browser_for = eko201.browser_for

BARE = "/api/eko202-qa-bare"


def with_bare_route(make_app: AppFactory) -> FastAPI:
    app = make_app()

    @app.get(BARE)
    def bare() -> dict[str, bool]:
        return {"reached": True}

    return app


def session_for(app: FastAPI, browser_for: Any, stub: oidc_stub.Stub, roles: list[str]) -> Browser:
    stub.access_overrides = probe.role_claims(client=roles)
    browser: Browser = browser_for(app)
    browser.login()
    assert browser.session is not None
    return browser


@pytest.mark.parametrize(
    "roles, expected",
    [([], 403), (["auditor"], 403), (["rep"], 200), (["administrator"], 403)],
    ids=["no-role", "unknown-role", "rep", "administrator"],
)
def test_qa_k01_route_declaring_no_dependency_refuses_a_role_less_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, roles: list[str], expected: int
) -> None:
    app = with_bare_route(make_app)
    browser = session_for(app, browser_for, stub, roles)
    assert browser.send("GET", BARE).status_code == expected


def test_qa_k01_contrast_route_declaring_no_dependency_answers_401_without_a_session(
    make_app: AppFactory, browser_for: Any
) -> None:
    app = with_bare_route(make_app)
    assert browser_for(app).send("GET", BARE).status_code == 401


CHANNELS: dict[str, dict[str, Any]] = {
    "header": {"headers": {"X-Role": "rep", "Role": "rep", "X-Roles": "rep"}},
    "query": {"params": {"role": "rep"}},
    "cookie": {"cookies": {"role": "rep", "roles": "rep"}},
}


@pytest.mark.parametrize("channel", sorted(CHANNELS))
def test_qa_k02_role_less_session_naming_rep_in_a_client_channel_stays_refused(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, channel: str
) -> None:
    app = make_app()
    recorder = probe.install_probe(app)
    browser = session_for(app, browser_for, stub, [])
    extra = CHANNELS[channel]
    saved = dict(browser.jar)
    browser.jar.update(extra.get("cookies", {}))
    try:
        status = browser.send(
            "GET", probe.CUSTOMERS, headers=extra.get("headers", {}), params=extra.get("params")
        ).status_code
    finally:
        browser.jar.clear()
        browser.jar.update(saved)
    assert status == 403
    assert recorder.received == []


def test_qa_k02_contrast_the_token_claim_rep_is_served(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    app = make_app()
    recorder = probe.install_probe(app)
    browser = session_for(app, browser_for, stub, ["rep"])
    assert browser.send("GET", probe.CUSTOMERS).status_code == 200
    assert len(recorder.received) == 1
