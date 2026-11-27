"""EKO-3-10 K-05 (G-1 B; ADR-0003-C33 as restated in the EKO-3-05 addendum draft): what the
Customers screen learns about archived customers comes from the caller's own visibility scope.

Under G-1 B the screen's empty default list makes two requests: `GET /api/customers` with no
`state`, then `GET /api/customers?state=archived`. The default view reached again through
Aktywni sends `state=active` (K-01 edge), so it is asked too. A rep R1 that owns no customer gets
answers byte-equal (status, body, headers but `Eko-Correlation-Id`) whether or not another rep R2
owns archived customers; once R1 owns an archived customer itself, its `state=archived` answer
carries it. A manager, with or without `rep`, gets every owner's archived customers; R2's own
answers do not move with R1's data.

Every value is synthetic (ADR-0005).
"""

import json
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import Browser
from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, Crm
from tests.runtime.eko305.conftest import EMPTY, answer, archive, customer, found, search

pytestmark = pytest.mark.runtime

R1, R2 = REP_A, REP_B
# The requests the screen makes for its empty default list (G-1 B), and the Aktywni default.
DEFAULT: dict[str, str] | None = None
ACTIVE = {"state": "active"}
ARCHIVED = {"state": "archived"}
SCREEN_REQUESTS: list[dict[str, str] | None] = [DEFAULT, ARCHIVED, ACTIVE]


def screen_answers(browser: Browser) -> list[tuple[int, bytes, list[tuple[str, str]]]]:
    return [answer(search(browser, params)) for params in SCREEN_REQUESTS]


def archived_customers(browser: Browser, names: list[str]) -> set[str]:
    """One customer per name, created under the browser's rep and archived by it."""
    ids = set()
    for name in names:
        customer_id = customer(browser, name)
        assert archive(browser, customer_id).status_code == 200
        ids.add(customer_id)
    return ids


def items(response: httpx.Response) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.text[:300]
    listed: list[dict[str, Any]] = response.json()["items"]
    return listed


ONE = ["Ferma Archiwalna R2 K05-1"]
SEVERAL = ["Ferma Archiwalna R2 K05-1", "Ferma Archiwalna R2 K05-2", "Ferma Archiwalna R2 K05-3"]
OTHERS_ARCHIVED = [pytest.param(ONE, id="one-archived"), pytest.param(SEVERAL, id="several")]


@pytest.mark.parametrize("names", OTHERS_ARCHIVED)
def test_k05_a_rep_with_no_customers_answers_the_same_whether_or_not_another_rep_has_archived_ones(
    crm: Crm, names: list[str]
) -> None:
    r1, r2 = crm.login(R1, ["rep"]), crm.login(R2, ["rep"])
    nothing = screen_answers(r1)
    assert [(status, json.loads(body)) for status, body, _ in nothing] == [(200, EMPTY)] * 3

    r2_archived = archived_customers(r2, names)
    # R2 owns only archived customers, and they are stored and visible to R2.
    assert found(r2) == set()
    assert found(r2, ARCHIVED) == r2_archived

    assert screen_answers(r1) == nothing


def test_k05_contrast_an_archived_customer_owned_by_r1_is_carried_by_r1s_archived_answer(
    crm: Crm,
) -> None:
    r1, r2 = crm.login(R1, ["rep"]), crm.login(R2, ["rep"])
    nothing = screen_answers(r1)
    archived_customers(r2, SEVERAL[1:])
    [own] = archived_customers(r1, SEVERAL[:1])

    default, archived, active = (search(r1, params) for params in SCREEN_REQUESTS)
    assert default.json() == EMPTY and active.json() == EMPTY
    assert items(archived) == [{"id": own, "name": SEVERAL[0], "country": "PL", "archived": True}]
    assert answer(archived) != nothing[1]


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(MANAGER, ["manager"], id="manager-without-rep"),
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
    ],
)
def test_k05_edge_a_manager_learns_of_every_owners_archived_customers(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    r1, r2 = crm.login(R1, ["rep"]), crm.login(R2, ["rep"])
    manager = crm.login(subject, roles)
    r2_archived = archived_customers(r2, SEVERAL[1:])
    assert items(search(manager, DEFAULT)) == []
    assert {item["id"] for item in items(search(manager, ARCHIVED))} == r2_archived

    r1_archived = archived_customers(r1, SEVERAL[:1])
    assert items(search(manager, DEFAULT)) == []
    assert items(search(manager, ACTIVE)) == []
    assert {item["id"] for item in items(search(manager, ARCHIVED))} == r1_archived | r2_archived


def test_k05_edge_r2s_own_answers_do_not_move_with_r1s_archived_customer(crm: Crm) -> None:
    r1, r2 = crm.login(R1, ["rep"]), crm.login(R2, ["rep"])
    r2_archived = archived_customers(r2, SEVERAL[1:])
    before = screen_answers(r2)
    assert {item["id"] for item in items(search(r2, ARCHIVED))} == r2_archived

    archived_customers(r1, SEVERAL[:1])
    assert screen_answers(r2) == before
