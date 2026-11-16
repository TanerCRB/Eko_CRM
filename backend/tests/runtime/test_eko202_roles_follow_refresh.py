"""EKO-2-02 K-05's mechanism on the local OIDC stub (a fast companion of the live carrier
`test_adr0003_c7_session_bound.py`): the caller's roles are rebuilt from every token the backend
verifies, so a refresh that carries fewer roles takes them away at once, and nothing is kept from
the token the session started with.
"""

from typing import Any

import pytest

from tests.runtime.eko201 import conftest as eko201
from tests.runtime.eko201.conftest import AppFactory, FakeClock, session_count
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

# The stub's access lifespan is 240 s; one second past it the next request refreshes.
EXPIRED = {"seconds": 241}


def test_k05_a_refreshed_token_without_manager_takes_manager_rights_away(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock
) -> None:
    from app.domain.caller import Role

    app = make_app()
    recorder = probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=["rep", "manager"])
    browser = browser_for(app)
    browser.login()
    assert browser.send("GET", probe.TEAM).status_code == 200

    stub.access_overrides = probe.role_claims(client=["rep"])
    # Contrast: until the access token expires, the roles it carries still apply.
    clock.advance(seconds=239)
    assert browser.send("GET", probe.TEAM).status_code == 200
    assert stub.refreshes() == []
    clock.advance(seconds=2)
    assert browser.send("GET", probe.TEAM).status_code == 403
    assert len(stub.refreshes()) == 1
    assert browser.send("GET", probe.CUSTOMERS).status_code == 200
    assert recorder.received[-1].roles == frozenset({Role.REP})


def test_k05_a_refreshed_token_with_no_role_left_answers_403_not_401(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock, pg: Postgres
) -> None:
    app = make_app()
    probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=["manager"])
    browser = browser_for(app)
    browser.login()
    stub.access_overrides = probe.role_claims(client=[])
    clock.advance(**EXPIRED)
    assert browser.send("GET", probe.TEAM).status_code == 403
    assert browser.send("GET", "/api/auth/session").status_code == 403
    assert session_count(pg) == 1


def test_k05_contrast_a_refused_refresh_answers_401_and_ends_the_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock, pg: Postgres
) -> None:
    app = make_app()
    probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=["rep", "manager"])
    browser = browser_for(app)
    browser.login()
    stub.refresh_mode = "refuse"
    clock.advance(**EXPIRED)
    assert browser.send("GET", probe.TEAM).status_code == 401
    assert session_count(pg) == 0


def test_k05_roles_gained_at_refresh_apply_from_that_token_on(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, clock: FakeClock
) -> None:
    app = make_app()
    probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=["rep"])
    browser = browser_for(app)
    browser.login()
    assert browser.send("GET", probe.TEAM).status_code == 403
    stub.access_overrides = probe.role_claims(client=["rep", "manager"])
    clock.advance(**EXPIRED)
    assert browser.send("GET", probe.TEAM).status_code == 200
