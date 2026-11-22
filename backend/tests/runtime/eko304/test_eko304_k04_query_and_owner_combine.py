"""EKO-3-04 K-04 (ACC-4, PRH-4): a text query and an owner filter combine; a customer is returned
only when both hold. Each condition alone returns more, so neither is dropped nor joined by OR.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_B, Crm
from tests.runtime.eko304.conftest import EMPTY, answer, customer, found, search

pytestmark = pytest.mark.runtime


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    return {
        "rep_a": rep_a,
        "a1": customer(rep_a, "Kowal Agro"),
        "a2": customer(rep_a, "Nowak"),
        "b1": customer(rep_b, "Kowal Rolny"),
    }


@pytest.mark.parametrize(
    "order",
    [
        pytest.param([("q", "kowal"), ("owner", REP_A)], id="query-first"),
        pytest.param([("owner", REP_A), ("q", "kowal")], id="owner-first"),
    ],
)
def test_k04_the_manager_gets_only_customers_matching_both(
    crm: Crm, owned: dict[str, Any], order: list[tuple[str, str]]
) -> None:
    assert found(crm.login(MANAGER, ["manager"]), order) == {owned["a1"]}


def test_k04_contrast_each_condition_alone_returns_more(crm: Crm, owned: dict[str, Any]) -> None:
    manager = crm.login(MANAGER, ["manager"])
    assert found(manager, {"q": "kowal"}) == {owned["a1"], owned["b1"]}
    assert found(manager, {"owner": REP_A}) == {owned["a1"], owned["a2"]}


def test_k04_edge_a_rep_naming_another_owner_gets_the_no_match_answer(
    owned: dict[str, Any],
) -> None:
    rep_a = owned["rep_a"]
    denied = search(rep_a, {"q": "kowal", "owner": REP_B})
    assert denied.json() == EMPTY
    assert answer(denied) == answer(search(rep_a, {"q": "zzqnigdzie"}))


def test_k04_edge_a_rep_naming_itself_gets_its_matching_customer(owned: dict[str, Any]) -> None:
    assert found(owned["rep_a"], {"q": "kowal", "owner": REP_A}) == {owned["a1"]}
