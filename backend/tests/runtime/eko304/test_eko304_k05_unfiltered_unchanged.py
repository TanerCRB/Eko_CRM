"""EKO-3-04 K-05 (ADR-0003 addendum of EKO-3-01, sections 2 to 4; ADR-0003-C34; G-5 A): with no
query and no filter the list behaves as EKO-3-01 proved, and the query parameters change no access
answer. A customer with no contacts and no town is listed; an administrator-only and a role-less
caller get the same 403 with or without `q` and `owner`, even an over-long one; a caller with no
session gets 401, never a 422 for its query. An empty or whitespace-only `q` and an empty `owner`
are no parameter at all.

The EKO-3-01 carriers (`tests/runtime/eko301/`) run unchanged; this file adds the cases the search
could break.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import ADMINISTRATOR, REP_A, REP_B, ROLE_LESS, Crm
from tests.runtime.eko304.conftest import EMPTY, answer, customer, email, found, search

pytestmark = pytest.mark.runtime

OVER_LONG = "q" * 2000
QUERIES: dict[str, Any] = {
    "none": None,
    "query": {"q": "ferma"},
    "owner": {"owner": REP_A},
    "both": {"q": "ferma", "owner": REP_A},
    "over-long-query": {"q": OVER_LONG},
    "over-long-owner": {"owner": OVER_LONG},
    "nul-query": {"q": "\x00"},
}


def test_k05_a_customer_without_contacts_or_town_is_in_the_unfiltered_list(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    bare = customer(rep, "Ferma Bez Niczego")
    with_contact = customer(
        rep, "Ferma Z Kontaktem", town="Wola Testowa", contacts=[email("k05@example.com")]
    )
    assert found(rep) == {bare, with_contact}


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(ADMINISTRATOR, ["administrator"], id="administrator-only"),
        pytest.param(ROLE_LESS, [], id="role-less"),
    ],
)
def test_k05_a_refused_caller_gets_the_same_403_whatever_the_query(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    customer(crm.login(REP_A, ["rep"]), "Ferma Testowa")
    browser = crm.login(subject, roles)
    answers = {label: search(browser, params) for label, params in QUERIES.items()}
    assert answers["none"].status_code == 403, answers["none"].text
    assert answers["none"].json() == {"detail": "not permitted"}
    for label, response in answers.items():
        assert answer(response) == answer(answers["none"]), label


def test_k05_a_caller_without_a_session_gets_401_whatever_the_query(crm: Crm) -> None:
    anonymous = crm.open_browser(crm.app)
    answers = {label: search(anonymous, params) for label, params in QUERIES.items()}
    assert answers["none"].status_code == 401, answers["none"].text
    for label, response in answers.items():
        assert answer(response) == answer(answers["none"]), label


def test_k05_contrast_a_rep_with_an_over_long_query_gets_422(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    assert search(rep, QUERIES["over-long-query"]).status_code == 422
    assert search(rep, QUERIES["over-long-owner"]).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"q": ""}, id="empty-query"),
        pytest.param({"q": "  \t "}, id="whitespace-query"),
        pytest.param({"owner": ""}, id="empty-owner"),
        pytest.param({"q": " ", "owner": ""}, id="both-empty"),
    ],
)
def test_k05_an_empty_parameter_is_no_parameter(crm: Crm, params: dict[str, str]) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    mine = {customer(rep_a, "Ferma A1"), customer(rep_a, "Sad A2")}
    customer(crm.login(REP_B, ["rep"]), "Ferma B1")
    assert answer(search(rep_a, params)) == answer(search(rep_a))
    assert found(rep_a, params) == mine


def test_k05_edge_a_rep_with_no_customers_gets_an_empty_list(crm: Crm) -> None:
    customer(crm.login(REP_B, ["rep"]), "Ferma B1")
    rep_a = crm.login(REP_A, ["rep"])
    assert search(rep_a).json() == EMPTY
    assert search(rep_a, {"q": " "}).json() == EMPTY
