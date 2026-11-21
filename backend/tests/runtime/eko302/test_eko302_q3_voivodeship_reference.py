"""EKO-3-02, Q-3 A (gate 1): one read-only API operation serves the voivodeship and county
mapping the backend validates with, from the same dated TERYT file, so the SPA takes its lists
from the server instead of a copy. It is a CRM operation: a session and an application role are
required, as for every operation not on the ADR-0003 lists.

Its every pair is accepted by the create rule, and a county outside its voivodeship is not, so
the two cannot drift apart.
"""

import json

import pytest

from tests.runtime.eko301.conftest import (
    MANAGER,
    REP_A,
    ROLE_LESS,
    Crm,
    create,
)
from tests.runtime.eko302.conftest import NAME, errors_at
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

REFERENCE = "/api/reference/voivodeships"
REGISTER = REPO_ROOT / "backend" / "app" / "domain" / "teryt_terc_2026-01-01.json"


def expected() -> dict[str, object]:
    document = json.loads(REGISTER.read_text(encoding="utf-8"))
    return {
        "as_of": document["as_of"],
        "voivodeships": [
            {"name": v["name"], "counties": [c["name"] for c in v["counties"]]}
            for v in document["voivodeships"]
        ],
    }


@pytest.mark.parametrize(("subject", "roles"), [(REP_A, ["rep"]), (MANAGER, ["manager"])])
def test_q3_the_reference_serves_the_register_file(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    browser = crm.login(subject, roles)
    response = browser.send("GET", REFERENCE)
    assert response.status_code == 200, response.text
    assert response.json() == expected()
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert crm.counts() == {"customer_contact": 0, "customer": 0}


def test_q3_every_served_pair_is_accepted_and_a_crossed_pair_is_not(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    served = rep.send("GET", REFERENCE).json()["voivodeships"]
    for voivodeship in (served[0], served[-1]):
        for county in voivodeship["counties"]:
            body = {"name": NAME, "voivodeship": voivodeship["name"], "county": county}
            assert create(rep, body).status_code == 201, (voivodeship["name"], county)
    crossed = {"name": NAME, "voivodeship": served[0]["name"], "county": served[-1]["counties"][0]}
    assert errors_at(create(rep, crossed)) == [("county",)]


def test_q3_without_a_session_401_and_without_a_role_403(crm: Crm) -> None:
    anonymous = crm.open_browser(crm.app)
    assert anonymous.send("GET", REFERENCE).status_code == 401
    role_less = crm.login(ROLE_LESS, [])
    refused = role_less.send("GET", REFERENCE)
    assert refused.status_code == 403, refused.text
    assert "mazowieckie" not in refused.text
