"""EKO-2-02 K-01 (ADR-0003-C5, *Roles*): the role gate on the application-wide access dependency.

Walks every API operation registered on the shipped `create_app()` (the probe injected by the test
process, gate-1 OQ-3 A) once per token role set. Each token is a real login through the local
OIDC stub, verified by the shipped verifier; only the access token's role claims differ between
walks. The exemption list is held here and subtracted from the walk (ADR-0003 addendum of
2026-10-28; gate-1 OQ-1 A): the role check cannot reach those three routes.
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

# EKO-2-01's carrier fixtures (real PostgreSQL, the OIDC stub, the shipped `create_app()`), bound
# here by name because they live in a sibling directory's conftest.
pg = eko201.pg
clean = eko201.clean
stub = eko201.stub
clock = eko201.clock
make_app = eko201.make_app
browser_for = eko201.browser_for

EXEMPT = frozenset({"/api/auth/login", "/api/auth/callback", "/api/health"})
PRODUCT_PROTECTED = frozenset({("GET", "/api/auth/session"), ("POST", "/api/auth/logout")})
REFUSED = {401, 403}
ALL_THREE = ["rep", "manager", "administrator"]

Walk = dict[tuple[str, str], int]


def operations(app: FastAPI) -> list[tuple[str, str]]:
    found = []
    for context in route_contexts(app):
        path = context.path or ""
        for method in sorted(getattr(context.route, "methods", None) or set()):
            if path.startswith("/api"):
                found.append((method, path))
    return found


def walk(make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, claims: Any) -> Walk:
    """Every operation, each from a fresh login whose access token carries `claims`."""
    app = make_app()
    probe.install_probe(app)
    walked = operations(app)
    assert probe.OPERATIONS | PRODUCT_PROTECTED <= set(walked), walked
    answered: Walk = {}
    for method, path in walked:
        stub.access_overrides = claims
        browser = browser_for(app)
        browser.login()
        assert browser.session is not None
        answered[(method, path)] = browser.send(method, path).status_code
    return answered


def protected(answered: Walk) -> Walk:
    return {op: status for op, status in answered.items() if op[1] not in EXEMPT}


def exempt(answered: Walk) -> Walk:
    return {op: status for op, status in answered.items() if op[1] in EXEMPT}


NO_APPLICATION_ROLE = {
    "a-none-of-the-three": probe.role_claims(client=["offline_access"]),
    "b-realm-roles-named-like-them": probe.role_claims(client=[], realm=ALL_THREE),
    "empty-claim": probe.role_claims(client=[]),
    "absent-claim": probe.role_claims(),
    "unknown-name": probe.role_claims(client=["auditor"]),
    "case-variant": probe.role_claims(client=["Manager", "REP", "Administrator"]),
    "fullwidth": probe.role_claims(client=["ｍａｎａｇｅｒ", "ｒｅｐ"]),
    "string-claim": probe.role_claims(client="manager"),
    "other-client": probe.role_claims(other_clients={"account": ALL_THREE}),
}


@pytest.mark.parametrize("variant", sorted(NO_APPLICATION_ROLE))
def test_k01_no_application_role_gets_403_on_every_non_exempt_route(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, variant: str
) -> None:
    answered = walk(make_app, browser_for, stub, NO_APPLICATION_ROLE[variant])
    assert set(protected(answered).values()) == {403}, answered
    # The three exempted routes are served to the same role-less session.
    assert {path for _, path in exempt(answered)} == EXEMPT
    assert not REFUSED & set(exempt(answered).values()), answered


def test_k01_administrator_only_gets_403_on_crm_data_routes(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    answered = walk(make_app, browser_for, stub, probe.role_claims(client=["administrator"]))
    for operation in probe.OPERATIONS:
        assert answered[operation] == 403, (operation, answered)
    # Not "deny everything": the same token is authenticated on the non-CRM operations.
    for operation in PRODUCT_PROTECTED:
        assert answered[operation] == 200, (operation, answered)


def test_k01_manager_and_administrator_answers_exactly_as_manager_alone(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    manager = walk(make_app, browser_for, stub, probe.role_claims(client=["manager"]))
    both = walk(make_app, browser_for, stub, probe.role_claims(client=["manager", "administrator"]))
    assert both == manager
    for operation in probe.OPERATIONS | PRODUCT_PROTECTED:
        assert manager[operation] == 200, (operation, manager)


def test_k01_contrast_rep_gets_the_crm_answer_where_role_less_and_administrator_get_403(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    rep = walk(make_app, browser_for, stub, probe.role_claims(client=["rep"]))
    for operation in probe.CRM_DATA_OPERATIONS | PRODUCT_PROTECTED:
        assert rep[operation] == 200, (operation, rep)
    # `rep` holds no manager rights.
    for operation in probe.MANAGER_OPERATIONS:
        assert rep[operation] == 403, (operation, rep)


def test_k01_contrast_health_is_served_without_a_session_while_the_walk_refuses(
    make_app: AppFactory, browser_for: Any
) -> None:
    app = make_app()
    probe.install_probe(app)
    browser = browser_for(app)
    assert browser.send("GET", "/api/health").status_code == 200
    assert browser.send("GET", probe.CUSTOMERS).status_code == 401


def test_k01_probe_body_and_answer_on_get_and_post(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    app = make_app()
    recorder = probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=["rep"])
    browser = browser_for(app)
    browser.login()
    read = browser.send("GET", probe.CUSTOMERS)
    changed = browser.send("POST", probe.CUSTOMERS, json={})
    assert (read.status_code, read.json()) == (200, {"operation": "read-customers"})
    assert (changed.status_code, changed.json()) == (200, {"operation": "change-customers"})
    assert len(recorder.received) == 2
