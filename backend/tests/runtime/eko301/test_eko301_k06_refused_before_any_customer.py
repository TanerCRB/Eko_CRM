"""EKO-3-01 K-06 (ADR-0003 addendum of 2026-11-16, "CRM-data refusal is the default") and
ADR-0003-C34 (addendum of EKO-3-01, section 4, O-2 A): no customer operation is served to an
administrator-only or role-less account, and the access answer comes before the request body is
decoded, so a body that is not JSON, or JSON that fails validation, gets the same answer as a
valid one and stores nothing.

The C34 walk reads every body-accepting operation from the shipped `create_app()`'s route table;
an operation with no valid body in `VALID_BODIES` fails the walk instead of being skipped.
"""

from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import ORIGIN, Browser
from tests.runtime.eko301.conftest import (
    ADMINISTRATOR,
    CUSTOMERS,
    MANAGER,
    REP_A,
    ROLE_LESS,
    Crm,
    created_id,
    customer_url,
)
from tests.support import eko202_probe as probe
from tests.support.c2_routes import body_routes

pytestmark = pytest.mark.runtime

NOT_PERMITTED = (403, {"detail": "not permitted"})
VALID_BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", CUSTOMERS): {
        "name": "Gospodarstwo Odmowa",
        "contacts": [{"kind": "phone", "value": "+48601000601", "primary": True}],
    },
}
BODIES: dict[str, dict[str, Any]] = {
    "not-json": {
        "content": b'{"name": "Gospodarstwo',
        "headers": {"content-type": "application/json"},
    },
    "fails-validation": {"json": {"name": "", "contacts": [{"kind": "fax", "value": ""}]}},
    "wrong-type": {"json": {"name": ["x"], "country": 7}},
}
REFUSED_ROLES = {
    "administrator-only": (ADMINISTRATOR, ["administrator"]),
    "role-less": (ROLE_LESS, []),
}


def answer(response: httpx.Response) -> tuple[int, Any]:
    return response.status_code, response.json()


@pytest.fixture
def existing(crm: Crm) -> str:
    return created_id(crm.login(REP_A, ["rep"]), {"name": "Gospodarstwo Przedstawiciela"})


@pytest.mark.parametrize("refused", sorted(REFUSED_ROLES))
def test_k06_every_customer_operation_is_refused_with_403(
    crm: Crm, existing: str, refused: str
) -> None:
    browser = crm.login(*REFUSED_ROLES[refused])
    before = crm.counts()
    assert answer(browser.send("GET", customer_url(existing))) == NOT_PERMITTED
    assert answer(browser.send("GET", CUSTOMERS)) == NOT_PERMITTED
    valid = VALID_BODIES[("POST", CUSTOMERS)]
    assert answer(browser.send("POST", CUSTOMERS, json=valid)) == NOT_PERMITTED
    for variant, kwargs in BODIES.items():
        assert answer(browser.send("POST", CUSTOMERS, **kwargs)) == NOT_PERMITTED, variant
    assert crm.counts() == before


def test_k06_contrast_manager_and_administrator_answers_as_manager_alone(
    crm: Crm, existing: str
) -> None:
    answers = []
    for subject, roles in ((MANAGER, ["manager"]), (MANAGER, ["manager", "administrator"])):
        browser = crm.login(subject, roles)
        read = browser.send("GET", customer_url(existing))
        listed = browser.send("GET", CUSTOMERS)
        created = browser.send("POST", CUSTOMERS, json=VALID_BODIES[("POST", CUSTOMERS)])
        answers.append((answer(read), answer(listed), answer(created)))
    assert answers[0] == answers[1]
    (read_status, record), (list_status, _), refused = answers[0]
    assert (read_status, record["id"], list_status) == (200, existing, 200)
    assert refused == NOT_PERMITTED


# ADR-0003-C34 ----------------------------------------------------------------------------------


def send(browser: Browser, method: str, path: str, origin: str | None, **kwargs: Any) -> Any:
    return answer(browser.send(method, path, origin=origin, **kwargs))


def test_c34_every_body_operation_answers_access_first_whatever_the_body(crm: Crm) -> None:
    routes = body_routes(crm.app)
    operations = {(r.method, r.path) for r in routes}
    assert operations, "no body-accepting operation: the walk would pass vacuously"
    assert operations <= set(VALID_BODIES), (
        f"no valid body known for {operations - set(VALID_BODIES)}"
    )
    callers: dict[str, tuple[Browser, str | None, Any]] = {
        "no-session": (crm.open_browser(crm.app), ORIGIN, (401, {"detail": "not authenticated"})),
        "no-session-no-origin": (
            crm.open_browser(crm.app),
            None,
            (403, {"detail": "origin refused"}),
        ),
        "foreign-origin": (
            crm.login(REP_A, ["rep"]),
            "https://elsewhere.test",
            (403, {"detail": "origin refused"}),
        ),
        "role-less": (crm.login(ROLE_LESS, []), ORIGIN, NOT_PERMITTED),
        "administrator-only": (crm.login(ADMINISTRATOR, ["administrator"]), ORIGIN, NOT_PERMITTED),
    }
    before = crm.counts()
    for method, path in sorted(operations):
        for label, (browser, origin, expected) in callers.items():
            valid = send(browser, method, path, origin, json=VALID_BODIES[(method, path)])
            assert valid == expected, (method, path, label)
            for variant, kwargs in BODIES.items():
                got = send(browser, method, path, origin, **kwargs)
                assert got == valid, (method, path, label, variant, got)
    assert crm.counts() == before


def test_c34_contrast_a_rep_with_a_body_that_is_not_json_gets_422(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = rep.send("POST", CUSTOMERS, **BODIES["not-json"])
    assert response.status_code == 422, response.text
    assert crm.counts() == before


def test_c34_a_route_registered_later_with_a_body_is_also_answered_access_first(
    crm: Crm,
) -> None:
    """EKO-2-02's probe: a body route added to the built application after `create_app()`."""
    probe.install_probe(crm.app)
    browser = crm.login(ADMINISTRATOR, ["administrator"])
    response = browser.send("POST", probe.CUSTOMERS, **BODIES["not-json"])
    assert answer(response) == NOT_PERMITTED
