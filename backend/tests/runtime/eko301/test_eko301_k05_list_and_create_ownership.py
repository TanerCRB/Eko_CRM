"""EKO-3-01 K-05 (ACC-4, PRH-4; C-2 A, C-3 A; ADR-0003-C33, list and create halves): a rep's plain
list holds exactly its own customers and the manager's holds all of them; every created customer
is owned by its creator, whatever the request names; an account holding `manager` without `rep`
is refused when it creates, and one holding both creates customers it owns.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import (
    MANAGER,
    REP_A,
    REP_AND_MANAGER,
    REP_B,
    Crm,
    create,
    created_id,
    customer_url,
    listed_ids,
)

pytestmark = pytest.mark.runtime


def owners(crm: Crm) -> dict[str, str]:
    return {str(i): o for i, o in crm.pg.rows("SELECT id, owner_subject FROM customer")}


def test_k05_each_reps_list_holds_exactly_its_own_customers(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    a_ids = {created_id(rep_a, {"name": f"Gospodarstwo A{n}"}) for n in (1, 2)}
    b_ids = {created_id(rep_b, {"name": "Gospodarstwo B1"})}
    assert listed_ids(rep_a) == a_ids
    assert listed_ids(rep_b) == b_ids
    assert owners(crm) == {**dict.fromkeys(a_ids, REP_A), **dict.fromkeys(b_ids, REP_B)}


def test_k05_contrast_a_the_managers_list_holds_all_three(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    every = {created_id(rep_a, {"name": f"Gospodarstwo A{n}"}) for n in (1, 2)}
    every.add(created_id(rep_b, {"name": "Gospodarstwo B1"}))
    assert listed_ids(crm.login(MANAGER, ["manager"])) == every
    assert listed_ids(crm.login(REP_AND_MANAGER, ["rep", "manager"])) == every


def test_k05_a_rep_with_none_gets_an_empty_list_and_one_with_one_a_list_of_one(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    created_id(rep_a, {"name": "Gospodarstwo A1"})
    created_id(rep_a, {"name": "Gospodarstwo A2"})
    assert listed_ids(rep_b) == set()
    only = created_id(rep_b, {"name": "Gospodarstwo B1"})
    assert listed_ids(rep_b) == {only}


NAMED_OWNERS: dict[str, dict[str, Any]] = {
    "owner": {"owner": REP_B},
    "owner_subject": {"owner_subject": REP_B},
    "owner-id": {"owner_id": REP_B},
    "subject": {"subject": REP_B},
}


@pytest.mark.parametrize("variant", sorted(NAMED_OWNERS))
def test_k05_a_create_naming_another_owner_never_makes_a_customer_owned_by_anyone_else(
    crm: Crm, variant: str
) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    response = create(rep_a, {"name": "Gospodarstwo Przejete", **NAMED_OWNERS[variant]})
    if response.status_code == 201:
        made = response.json()["id"]
        assert rep_b.send("GET", customer_url(made)).status_code == 404
        assert made not in listed_ids(rep_b)
    else:
        assert response.status_code == 422, response.text
    assert set(owners(crm).values()) <= {REP_A}
    assert listed_ids(rep_b) == set()


def test_k05_a_manager_only_account_is_refused_when_it_creates_and_nothing_is_stored(
    crm: Crm,
) -> None:
    created_id(crm.login(REP_A, ["rep"]), {"name": "Gospodarstwo A1"})
    manager = crm.login(MANAGER, ["manager"])
    before_list, before_counts = listed_ids(manager), crm.counts()
    response = create(manager, {"name": "Gospodarstwo Kierownika"})
    assert (response.status_code, response.json()) == (403, {"detail": "not permitted"})
    assert listed_ids(manager) == before_list
    assert crm.counts() == before_counts


def test_k05_contrast_b_rep_and_manager_creates_a_customer_it_owns(crm: Crm) -> None:
    both = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    made = created_id(both, {"name": "Gospodarstwo Kierownika"})
    assert made in listed_ids(both)
    assert owners(crm) == {made: REP_AND_MANAGER}
