"""EKO-3-04 assumptions for gate 2 (the backend report's ledger, A-01 to A-03): gaps the criteria
leave open, closed by the backend developer and pinned here so the human can accept or reject each.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, REP_B, Crm
from tests.runtime.eko304.conftest import EMPTY, answer, customer, found, search

pytestmark = pytest.mark.runtime


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep_a = crm.login(REP_A, ["rep"])
    customer(crm.login(REP_B, ["rep"]), "Sklep B1")
    return {
        "rep": rep_a,
        "shop": customer(rep_a, "Sklep A1"),
        "plain": customer(rep_a, "Zwykły A2"),
    }


def test_a01_a_repeated_parameter_is_read_as_its_last_value(owned: dict[str, Any]) -> None:
    rep = owned["rep"]
    assert answer(search(rep, [("q", "sklep"), ("q", "zwykły")])) == answer(
        search(rep, {"q": "zwykły"})
    )
    assert found(rep, [("owner", REP_A), ("owner", REP_B)]) == set()
    assert found(rep, [("owner", REP_B), ("owner", REP_A)]) == {owned["shop"], owned["plain"]}


@pytest.mark.parametrize(
    ("raw", "parameter"),
    [
        pytest.param("q=%FF", "q", id="query"),
        pytest.param("owner=%FF", "owner", id="owner"),
    ],
)
def test_a02_invalid_percent_encoded_utf_8_is_a_422_string_unicode_at_its_parameter(
    owned: dict[str, Any], raw: str, parameter: str
) -> None:
    response = owned["rep"].send("GET", f"/api/customers?{raw}")
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert (error["type"], error["loc"]) == ("string_unicode", ["query", parameter])


def test_a02_contrast_invalid_utf_8_in_another_parameter_is_ignored(owned: dict[str, Any]) -> None:
    response = owned["rep"].send("GET", "/api/customers?other=%FF")
    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["items"]} == {owned["shop"], owned["plain"]}


def test_a03_both_parameters_rejected_give_one_error_each_query_first(
    owned: dict[str, Any],
) -> None:
    response = search(owned["rep"], {"owner": "o" * 256, "q": "q" * 255})
    assert response.status_code == 422, response.text
    assert [e["loc"] for e in response.json()["detail"]] == [["query", "q"], ["query", "owner"]]
    assert search(owned["rep"], {"q": "zzqnigdzie"}).json() == EMPTY
