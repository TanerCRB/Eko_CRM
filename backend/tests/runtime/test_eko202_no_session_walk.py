"""EKO-2-02 K-06 legs 1 and 2 (ADR-0003-C4 as restated 2026-10-28, *Account lifecycle*): after
this task, every API operation outside exactly {login start, login callback, health} answers 401
without a session, and the access dependency's exemption list holds exactly those three.

The walk reads the route table of the shipped `create_app()` as served, with EKO-2-02's probe
injected by the test process, so the probe appears in the walk and a route registered after the
application was built is covered too.
"""

from typing import Any

import pytest
from fastapi import FastAPI

from tests.runtime.eko201 import conftest as eko201
from tests.runtime.eko201.conftest import AppFactory
from tests.support import eko202_probe as probe
from tests.support import oidc_stub
from tests.support.api_surface import route_contexts

pytestmark = pytest.mark.runtime

# EKO-2-01's carrier fixtures, bound here by name because they live in a sibling conftest.
pg = eko201.pg
clean = eko201.clean
stub = eko201.stub
clock = eko201.clock
make_app = eko201.make_app
browser_for = eko201.browser_for

EXEMPT = frozenset({"/api/auth/login", "/api/auth/callback", "/api/health"})
# The product's operations at this task's completion: EKO-2-02 adds none.
PRODUCT = frozenset(
    {
        ("GET", "/api/health"),
        ("HEAD", "/api/health"),
        ("GET", "/api/auth/login"),
        ("GET", "/api/auth/callback"),
        ("GET", "/api/auth/session"),
        ("POST", "/api/auth/logout"),
    }
)
HIDDEN = "/api/eko202-hidden"


def operations(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, context.path or "")
        for context in route_contexts(app)
        for method in getattr(context.route, "methods", None) or set()
        if (context.path or "").startswith("/api")
    }


def test_k06_the_task_adds_no_product_operation(make_app: AppFactory) -> None:
    assert operations(make_app()) == PRODUCT


def test_k06_without_a_session_everything_outside_exactly_three_routes_answers_401(
    make_app: AppFactory, browser_for: Any
) -> None:
    app = make_app()
    probe.install_probe(app)
    walked = operations(app)
    assert probe.OPERATIONS <= walked, walked
    browser = browser_for(app)
    answered = {(m, p): browser.send(m, p).status_code for m, p in sorted(walked)}
    not_401 = {path for (_, path), status in answered.items() if status != 401}
    assert not_401 == set(EXEMPT), answered


def test_k06_exemption_list_is_exactly_the_three_routes(make_app: AppFactory) -> None:
    from app import main

    assert main.PUBLIC_PATHS == EXEMPT
    app = make_app()
    public = app.state.auth.public_routes
    by_route = {id(c.route): c.path or "" for c in route_contexts(app)}
    # Health is two route objects (GET and HEAD); every public object is on one of three paths.
    assert sorted(by_route[id(route)] for route in public) == sorted([*EXEMPT, "/api/health"])


def test_k06_a_route_hidden_from_the_openapi_document_is_still_walked_and_refused(
    make_app: AppFactory, browser_for: Any
) -> None:
    app = make_app()

    @app.post(HIDDEN, include_in_schema=False)
    def hidden() -> dict[str, bool]:
        return {"reached": True}

    assert HIDDEN not in app.openapi()["paths"]
    assert ("POST", HIDDEN) in operations(app)
    assert browser_for(app).send("POST", HIDDEN).status_code == 401


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS"])
def test_k06_head_and_options_without_a_session_reach_no_protected_answer(
    make_app: AppFactory, browser_for: Any, method: str
) -> None:
    app = make_app()
    probe.install_probe(app)
    browser = browser_for(app)
    paths = {path for _, path in operations(app)}
    for path in sorted(paths - EXEMPT):
        # No route declares the method: the router answers 405 before any handler; else 401.
        assert browser.send(method, path).status_code in {401, 405}, (method, path)
    assert browser.send("HEAD", "/api/health").status_code == 200


def test_k06_contrast_a_session_gets_authenticated_answers_while_health_stays_anonymous(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    app = make_app()
    probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=["rep"])
    browser = browser_for(app)
    browser.login()
    for method, path in sorted(probe.CRM_DATA_OPERATIONS | {("GET", "/api/auth/session")}):
        assert browser.send(method, path).status_code == 200, (method, path)
    anonymous = browser_for(app)
    assert anonymous.send("GET", "/api/health").status_code == 200
