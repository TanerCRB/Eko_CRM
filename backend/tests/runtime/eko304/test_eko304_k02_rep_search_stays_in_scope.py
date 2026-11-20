"""EKO-3-04 K-02 (ACC-4, PRH-4, ACC-8; ADR-0003-C33 as restated at gate 1 of EKO-3-04): a rep's
search never returns another rep's customer, whether the query matches it by name, by town or by
a contact value, and its answer is byte-equal to the answer for a query that matches nothing: the
same status, body (exactly `{"items": []}`) and headers, `Eko-Correlation-Id` aside.

Contrasts change one element: the caller (the owner, a manager, a `rep`+`manager` account), or the
data (a string that also matches rep A's own customer, so the search does run for rep A).
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, Crm
from tests.runtime.eko304.conftest import EMPTY, answer, customer, email, found, phone, search

pytestmark = pytest.mark.runtime

NOWHERE = "zzqnigdzie"
UNIQUE = {
    "name": "bxqnazwa",
    "town": "bxqmiasto",
    "phone": "600700701",
    "e-mail": "bxqpoczta",
}


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    a1 = customer(rep_a, "Ferma Ayq", town="Wola Ayq", contacts=[phone("+48600700900")])
    b_name = customer(rep_b, "Ferma Bxqnazwa")
    b_town = customer(rep_b, "Sad Byq", town="Bxqmiasto")
    b_contact = customer(
        rep_b, "Sad Bzq", contacts=[phone("+48600700701"), email("bxqpoczta@example.com")]
    )
    return {
        "rep_a": rep_a,
        "rep_b": rep_b,
        "a1": a1,
        "name": b_name,
        "town": b_town,
        "phone": b_contact,
        "e-mail": b_contact,
    }


@pytest.mark.parametrize("field", sorted(UNIQUE))
def test_k02_another_reps_match_is_answered_as_a_query_matching_nothing(
    owned: dict[str, Any], field: str
) -> None:
    rep_a = owned["rep_a"]
    denied = search(rep_a, {"q": UNIQUE[field]})
    nothing = search(rep_a, {"q": NOWHERE})
    assert denied.status_code == 200, denied.text
    assert denied.json() == EMPTY
    assert answer(denied) == answer(nothing)


@pytest.mark.parametrize("field", sorted(UNIQUE))
@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(REP_B, ["rep"], id="the-owner"),
        pytest.param(MANAGER, ["manager"], id="manager"),
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
    ],
)
def test_k02_contrast_the_owner_or_a_manager_gets_the_customer(
    crm: Crm, owned: dict[str, Any], field: str, subject: str, roles: list[str]
) -> None:
    reader = owned["rep_b"] if subject == REP_B else crm.login(subject, roles)
    assert found(reader, {"q": UNIQUE[field]}) == {owned[field]}


def test_k02_contrast_a_string_matching_both_reps_gives_rep_a_only_its_own(
    owned: dict[str, Any],
) -> None:
    assert found(owned["rep_a"], {"q": "ferma"}) == {owned["a1"]}
    assert found(owned["rep_b"], {"q": "ferma"}) == {owned["name"]}


def test_k02_edge_one_of_rep_bs_customers_among_many_of_rep_as(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    mine = {customer(rep_a, f"Ferma Ayq {n}") for n in range(6)}
    customer(rep_b, "Ferma Bxqnazwa")
    assert found(rep_a, {"q": "ferma"}) == mine
    denied = search(rep_a, {"q": "bxqnazwa"})
    assert denied.json() == EMPTY
    assert answer(denied) == answer(search(rep_a, {"q": NOWHERE}))


def test_k02_edge_a_rep_with_no_customers_gets_the_same_empty_answer(crm: Crm) -> None:
    rep_b = crm.login(REP_B, ["rep"])
    customer(rep_b, "Ferma Bxqnazwa", town="Bxqmiasto")
    rep_a = crm.login(REP_A, ["rep"])
    for query in ("bxqnazwa", "bxqmiasto"):
        denied = search(rep_a, {"q": query})
        assert denied.json() == EMPTY
        assert answer(denied) == answer(search(rep_a, {"q": NOWHERE}))
