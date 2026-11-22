"""EKO-3-04 K-03 (PRH-4; G-3 A, G-5 A; ADR-0003 addendum of EKO-3-04, Q-3 A): the manager narrows
the list to one owner subject, compared byte-wise; a rep's owner filter is intersected with the
rep's own scope, so it never widens it, and an existing owner with customers and a well-formed
subject that owns nothing get the same answer, byte-equal to a query that matches nothing.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, Crm
from tests.runtime.eko304.conftest import NOBODY, answer, customer, found, search

pytestmark = pytest.mark.runtime


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    return {
        "rep_a": rep_a,
        "a": {customer(rep_a, "Ferma A1"), customer(rep_a, "Ferma A2")},
        "b": {customer(rep_b, "Ferma B1")},
    }


def test_k03_the_manager_narrows_the_list_to_one_owner(crm: Crm, owned: dict[str, Any]) -> None:
    manager = crm.login(MANAGER, ["manager"])
    assert found(manager, {"owner": REP_B}) == owned["b"]
    assert found(manager, {"owner": REP_A}) == owned["a"]
    assert found(manager) == owned["a"] | owned["b"]


def test_k03_a_reps_filter_naming_another_owner_or_nobody_is_answered_as_no_match(
    owned: dict[str, Any],
) -> None:
    rep_a = owned["rep_a"]
    other = search(rep_a, {"owner": REP_B})
    nobody = search(rep_a, {"owner": NOBODY})
    nothing = search(rep_a, {"q": "zzqnigdzie"})
    assert other.status_code == 200, other.text
    assert other.json() == {"items": []}
    assert answer(other) == answer(nobody) == answer(nothing)


def test_k03_a_reps_filter_naming_itself_gives_its_own_customers(owned: dict[str, Any]) -> None:
    assert found(owned["rep_a"], {"owner": REP_A}) == owned["a"]


def test_k03_contrast_the_manager_sending_the_same_filter_gets_bs_customer(
    crm: Crm, owned: dict[str, Any]
) -> None:
    assert found(owned["rep_a"], {"owner": REP_B}) == set()
    assert found(crm.login(MANAGER, ["manager"]), {"owner": REP_B}) == owned["b"]


def test_k03_edge_a_subject_differing_only_in_case_is_another_subject(
    crm: Crm, owned: dict[str, Any]
) -> None:
    assert REP_B.upper() != REP_B
    assert found(crm.login(MANAGER, ["manager"]), {"owner": REP_B.upper()}) == set()


def test_k03_edge_rep_and_manager_narrows_as_the_manager(crm: Crm, owned: dict[str, Any]) -> None:
    both = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    assert found(both, {"owner": REP_B}) == owned["b"]
    assert found(both, {"owner": REP_A}) == owned["a"]


def test_k03_edge_a_manager_filtering_by_its_own_subject_gets_nothing(
    crm: Crm, owned: dict[str, Any]
) -> None:
    assert found(crm.login(MANAGER, ["manager"]), {"owner": MANAGER}) == set()


def test_k03_edge_an_empty_owner_is_no_filter(crm: Crm, owned: dict[str, Any]) -> None:
    rep_a = owned["rep_a"]
    assert answer(search(rep_a, {"owner": ""})) == answer(search(rep_a))
    manager = crm.login(MANAGER, ["manager"])
    assert found(manager, {"owner": ""}) == owned["a"] | owned["b"]
