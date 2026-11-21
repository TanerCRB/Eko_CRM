"""EKO-3-02, the gaps the criteria leave open and how this change closes them (assumption ledger
A-02, A-03, A-07, A-10 of the developer's report), each pinned so the human can accept or reject
it at gate 2. Synthetic values only; NIPs built at run time (G-7 A).
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create, created_id
from tests.runtime.eko302.conftest import NAME, errors_at, stored
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime


@pytest.mark.parametrize(
    "dependent",
    [
        {"postal_code": "00950"},
        {"voivodeship": "nadwiślańskie"},
        {"county": "bielski"},
        {"tax_id": "PL"},
    ],
)
def test_a02_an_invalid_country_leaves_the_country_dependent_fields_unjudged(
    crm: Crm, dependent: dict[str, Any]
) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    assert errors_at(create(rep, {"name": NAME, "country": "XX", **dependent})) == [("country",)]
    assert crm.counts() == before


@pytest.mark.parametrize("prefix", ["Pl", "pL"])
def test_a03_a_mixed_case_pl_prefix_is_removed_like_pl(crm: Crm, prefix: str) -> None:
    nip = nips.valid_nip(1203)
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "tax_id": prefix + nip})
    assert stored(crm, customer_id)["nip"] == nip


@pytest.mark.parametrize("field", ["voivodeship", "county"])
def test_a07_a_region_name_past_its_raw_cap_is_refused_at_its_field(crm: Crm, field: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    body = {"name": NAME, "voivodeship": "podlaskie", field: "x" * 257}
    response = create(rep, body)
    assert errors_at(response) == [(field,)]
    assert response.json()["detail"][0]["type"] == "string_too_long"
    assert crm.counts() == before


@pytest.mark.parametrize("not_given", [None, "", "  "])
def test_a10_a_foreign_voivodeship_or_county_not_given_is_no_refusal(
    crm: Crm, not_given: Any
) -> None:
    rep = crm.login(REP_A, ["rep"])
    body = {"name": NAME, "country": "DE", "voivodeship": not_given, "county": not_given}
    row = stored(crm, created_id(rep, body))
    assert (row["voivodeship"], row["county"]) == (None, None)
