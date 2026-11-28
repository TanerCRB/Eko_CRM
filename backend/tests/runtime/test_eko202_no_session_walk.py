"""EKO-2-02 K-06 legs 1 to 3 (ADR-0003-C4 as restated 2026-10-28, *Account lifecycle*, and the
ADR-0003 roles addendum of EKO-2-02): after this task, every API operation outside exactly {login
start, login callback, health} answers 401 without a session; the access dependency's exemption
list holds exactly those three; and the role-free and non-CRM lists equal the lists held here,
resolve to exactly the served route objects, and fail the build when an entry is unserved, shares
a path with the exemption list, or is role-free without being non-CRM.

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
# The product's operations: EKO-2-02 added none; EKO-3-01 adds the three customer operations
# (decision H6-B A on Issue #195); EKO-3-02 the voivodeship reference (Q-3 A on Issue #208);
# EKO-3-08 the manager's list of reps (G-4 A on Issue #216); EKO-3-05 customer edit, archive and
# restore (Q-5 on Issue #253); EKO-4-01 visit create, read, list and period list (Issue #268).
PRODUCT = frozenset(
    {
        ("GET", "/api/health"),
        ("HEAD", "/api/health"),
        ("GET", "/api/auth/login"),
        ("GET", "/api/auth/callback"),
        ("GET", "/api/auth/session"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/customers"),
        ("GET", "/api/customers"),
        ("GET", "/api/customers/{customer_id}"),
        ("PUT", "/api/customers/{customer_id}"),
        ("POST", "/api/customers/{customer_id}/archive"),
        ("POST", "/api/customers/{customer_id}/restore"),
        ("GET", "/api/reference/voivodeships"),
        ("GET", "/api/reps"),
        ("POST", "/api/visits"),
        ("GET", "/api/visits"),
        ("GET", "/api/visits/period"),
        ("GET", "/api/visits/{visit_id}"),
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


ROLE_FREE = frozenset({("POST", "/api/auth/logout")})
NON_CRM = frozenset({("GET", "/api/auth/session"), ("POST", "/api/auth/logout")})


def resolved(app: FastAPI, routes: tuple[object, ...]) -> set[tuple[str, str]]:
    """The (method, path) operations the given route objects serve, as served."""
    return {
        (method, context.path or "")
        for context in route_contexts(app)
        if any(context.route is route for route in routes)
        for method in getattr(context.route, "methods", None) or set()
    }


def test_k06_role_free_and_non_crm_lists_equal_the_held_lists(make_app: AppFactory) -> None:
    from app import main

    assert main.ROLE_FREE_OPERATIONS == ROLE_FREE
    assert main.NON_CRM_OPERATIONS == NON_CRM
    assert ROLE_FREE <= NON_CRM
    assert not {path for _, path in NON_CRM} & set(main.PUBLIC_PATHS)
    app = make_app()
    assert len(app.state.role_free_routes) == len(ROLE_FREE)
    assert len(app.state.non_crm_routes) == len(NON_CRM)
    assert resolved(app, app.state.role_free_routes) == ROLE_FREE
    assert resolved(app, app.state.non_crm_routes) == NON_CRM


BROKEN_LISTS = {
    "unserved-method": (ROLE_FREE, NON_CRM | {("GET", "/api/auth/logout")}),
    "unserved-trailing-slash": (ROLE_FREE, NON_CRM | {("GET", "/api/auth/session/")}),
    "unserved-case": (ROLE_FREE, NON_CRM | {("GET", "/api/Auth/session")}),
    "unserved-role-free": (
        ROLE_FREE | {("DELETE", "/api/auth/logout")},
        NON_CRM | {("DELETE", "/api/auth/logout")},
    ),
    "exempt-in-non-crm": (ROLE_FREE, NON_CRM | {("GET", "/api/health")}),
    "exempt-in-both": (
        ROLE_FREE | {("GET", "/api/auth/login")},
        NON_CRM | {("GET", "/api/auth/login")},
    ),
    "role-free-not-non-crm": (
        ROLE_FREE | {("GET", "/api/auth/session")},
        frozenset({("POST", "/api/auth/logout")}),
    ),
    "role-free-missing-from-non-crm": (ROLE_FREE, frozenset({("GET", "/api/auth/session")})),
}


@pytest.mark.parametrize("case", sorted(BROKEN_LISTS))
def test_k06_building_fails_on_an_unserved_exempt_or_non_subset_list_entry(
    make_app: AppFactory, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from app import main

    # Contrast: the lists as shipped build.
    assert make_app().state.non_crm_routes
    role_free, non_crm = BROKEN_LISTS[case]
    monkeypatch.setattr(main, "ROLE_FREE_OPERATIONS", frozenset(role_free))
    monkeypatch.setattr(main, "NON_CRM_OPERATIONS", frozenset(non_crm))
    with pytest.raises(SystemExit):
        make_app()
