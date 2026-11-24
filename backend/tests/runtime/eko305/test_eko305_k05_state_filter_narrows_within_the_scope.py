"""EKO-3-05 K-05 (ACC-4, PRH-4, ACC-8; G-2 A, Q-2 A, Q-5; ADR-0003-C33 as restated in the EKO-3-05
addendum draft): the list's `state` parameter narrows to `active`, `archived` or `both`, and an
empty or absent one means active. It combines with `q` and `owner` by AND, and it never widens a
rep's scope: under every value a rep gets none of rep B's customers, and a rep's search that only
rep B's archived customer matches answers byte-equal to a search that matches nothing.

Every item carries its stored `archived` state, never the state the request asked for. A value
outside the closed set, compared byte-wise, is a 422 naming `state` that repeats no value.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, Crm
from tests.runtime.eko305.conftest import (
    EMPTY,
    answer,
    archive,
    customer,
    email,
    found,
    listed_items,
    phone,
    search,
)

pytestmark = pytest.mark.runtime

TWIN = "Ferma Bliźniacza K05"


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    ids = {
        "a-active": customer(rep_a, "Ferma Czynna A", town="Wola A"),
        "a-archived": customer(rep_a, TWIN, town="Wola A"),
        "b-active": customer(rep_b, "Ferma Czynna B"),
        "b-archived": customer(
            rep_b,
            TWIN,
            town="Bxqzarchiwum",
            contacts=[phone("+48600705001"), email("bxqarchiwum@example.com")],
        ),
    }
    assert archive(rep_a, ids["a-archived"]).status_code == 200
    assert archive(rep_b, ids["b-archived"]).status_code == 200
    return {"rep_a": rep_a, "rep_b": rep_b, **ids}


def named(owned: dict[str, Any], *keys: str) -> set[str]:
    return {owned[key] for key in keys}


DEFAULTS: list[Any] = [None, {"state": ""}, {"state": "active"}]


def test_k05_each_state_value_gives_exactly_the_owners_set(owned: dict[str, Any]) -> None:
    rep_a = owned["rep_a"]
    for params in DEFAULTS:
        assert found(rep_a, params) == named(owned, "a-active"), params
    assert found(rep_a, {"state": "archived"}) == named(owned, "a-archived")
    assert found(rep_a, {"state": "both"}) == named(owned, "a-active", "a-archived")


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(MANAGER, ["manager"], id="manager"),
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
    ],
)
def test_k05_each_state_value_gives_exactly_the_managers_set(
    crm: Crm, owned: dict[str, Any], subject: str, roles: list[str]
) -> None:
    manager = crm.login(subject, roles)
    for params in DEFAULTS:
        assert found(manager, params) == named(owned, "a-active", "b-active"), params
    assert found(manager, {"state": "archived"}) == named(owned, "a-archived", "b-archived")
    assert found(manager, {"state": "both"}) == named(
        owned, "a-active", "a-archived", "b-active", "b-archived"
    )


def test_k05_the_state_combines_with_the_query_and_the_owner_filter(
    crm: Crm, owned: dict[str, Any]
) -> None:
    rep_a, manager = owned["rep_a"], crm.login(MANAGER, ["manager"])
    assert found(rep_a, {"q": "bliźniacza", "state": "archived"}) == named(owned, "a-archived")
    assert found(rep_a, {"q": "bliźniacza"}) == set()
    assert found(rep_a, {"q": "czynna", "state": "both"}) == named(owned, "a-active")
    assert found(manager, {"q": "bliźniacza", "state": "archived"}) == named(
        owned, "a-archived", "b-archived"
    )
    assert found(manager, {"owner": REP_B, "state": "archived"}) == named(owned, "b-archived")
    assert found(manager, {"owner": REP_B}) == named(owned, "b-active")
    assert found(manager, {"owner": REP_A, "state": "both"}) == named(
        owned, "a-active", "a-archived"
    )
    assert found(manager, {"owner": REP_A, "q": "wola", "state": "archived"}) == named(
        owned, "a-archived"
    )
    assert found(manager, {"owner": REP_B, "q": "czynna", "state": "archived"}) == set()


@pytest.mark.parametrize("state", ["", "active", "archived", "both"])
def test_k05_a_reps_list_never_holds_another_reps_customer(
    owned: dict[str, Any], state: str
) -> None:
    rep_a = owned["rep_a"]
    for params in (
        {"state": state},
        {"state": state, "q": "ferma"},
        {"state": state, "owner": REP_B},
    ):
        assert not found(rep_a, params) & named(owned, "b-active", "b-archived"), params
    assert found(rep_a, {"state": state, "owner": REP_B}) == set()


@pytest.mark.parametrize("state", ["archived", "both"])
@pytest.mark.parametrize("term", ["bxqzarchiwum", "600705001", "bxqarchiwum@"])
def test_k05_a_reps_search_matching_only_another_reps_archived_customer_answers_as_nothing(
    owned: dict[str, Any], state: str, term: str
) -> None:
    rep_a = owned["rep_a"]
    denied = search(rep_a, {"q": term, "state": state})
    nothing = search(rep_a, {"q": "zzqnigdzie", "state": state})
    assert denied.status_code == 200, denied.text
    assert denied.json() == EMPTY
    assert answer(denied) == answer(nothing)


def test_k05_contrast_the_managers_archived_list_holds_rep_bs_archived_customer(
    crm: Crm, owned: dict[str, Any]
) -> None:
    manager = crm.login(MANAGER, ["manager"])
    assert owned["b-archived"] in found(manager, {"q": "bxqzarchiwum", "state": "archived"})


def test_k05_every_item_carries_its_stored_state(crm: Crm, owned: dict[str, Any]) -> None:
    manager = crm.login(MANAGER, ["manager"])
    stored = {
        str(row[0]): row[1] is not None
        for row in crm.pg.rows("SELECT id, archived_at FROM customer")
    }
    for state in ("active", "archived", "both"):
        items = listed_items(manager, {"state": state})
        assert {item["id"]: item["archived"] for item in items} == {
            item["id"]: stored[item["id"]] for item in items
        }
        assert all(set(item) == {"id", "name", "country", "archived"} for item in items)
    assert {item["archived"] for item in listed_items(manager, {"state": "both"})} == {True, False}


INVALID = ["Active", " active", "active ", "ACTIVE", "all", "deleted", "archived,both", "0"]


def test_k05_a_state_outside_the_closed_set_is_a_422_naming_state_and_repeating_no_value(
    owned: dict[str, Any],
) -> None:
    rep_a = owned["rep_a"]
    answers = {value: search(rep_a, {"state": value}) for value in INVALID}
    first = answers[INVALID[0]]
    assert first.status_code == 422, first.text
    [error] = first.json()["detail"]
    assert (error["type"], error["loc"]) == ("value_error", ["query", "state"])
    # One body for every value: none of them is repeated in it.
    for value, response in answers.items():
        assert response.content == first.content, value


def test_k05_invalid_percent_encoded_utf_8_in_state_is_a_422_string_unicode(
    owned: dict[str, Any],
) -> None:
    response = owned["rep_a"].send("GET", "/api/customers?state=%FF")
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert (error["type"], error["loc"]) == ("string_unicode", ["query", "state"])


def test_k05_edge_a_repeated_state_is_read_as_its_last_value(owned: dict[str, Any]) -> None:
    rep_a = owned["rep_a"]
    assert found(rep_a, [("state", "active"), ("state", "archived")]) == named(owned, "a-archived")
    assert found(rep_a, [("state", "archived"), ("state", "active")]) == named(owned, "a-active")
