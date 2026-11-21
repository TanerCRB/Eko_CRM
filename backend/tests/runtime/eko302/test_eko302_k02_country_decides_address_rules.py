"""EKO-3-02 K-02 (CUS-3, CUS-4; C-3 A): the country decides the address rules. For Poland, sent
or defaulted, the postal code must be `00-000` in ASCII digits; for any other country it is free
text, and a voivodeship or county is refused with a field error and nothing is stored.

Sent straight to the API by a rep's real session, never through the SPA. Synthetic values only.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create, created_id, customer_url
from tests.runtime.eko302.conftest import NAME, errors_at, stored

pytestmark = pytest.mark.runtime

FULL_WIDTH = "００-９５０"
ARABIC_INDIC = "٠٠-٩٥٠"
REJECTED_POLISH = {
    "no-hyphen": "00950",
    "six-digits": "00-9500",
    "one-then-four": "0-0950",
    "space-for-hyphen": "00 950",
    "full-width-digits": FULL_WIDTH,
    "arabic-indic-digits": ARABIC_INDIC,
    "letters": "AB-CDE",
    "en-dash": "00–950",
}
REGION = {"voivodeship": "mazowieckie", "county": "warszawski zachodni"}


def refused_at(crm: Crm, body: dict[str, Any]) -> list[tuple[Any, ...]]:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = create(rep, body)
    locations = errors_at(response)
    assert crm.counts() == before
    return locations


@pytest.mark.parametrize("variant", sorted(REJECTED_POLISH))
def test_k02_polish_postal_code_shape(crm: Crm, variant: str) -> None:
    body = {"name": NAME, "country": "PL", "postal_code": REJECTED_POLISH[variant]}
    assert refused_at(crm, body) == [("postal_code",)]


def test_k02_a_polish_postal_code_is_trimmed_and_accepted(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "country": "PL", "postal_code": " 00-950 "})
    assert rep.send("GET", customer_url(customer_id)).json()["postal_code"] == "00-950"
    assert stored(crm, customer_id)["postal_code"] == "00-950"


@pytest.mark.parametrize("postal_code", ["00950", "00-950", "PL-00950", "SW1A 1AA", FULL_WIDTH])
def test_k02_foreign_postal_code_free_text(crm: Crm, postal_code: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "country": "DE", "postal_code": postal_code})
    assert rep.send("GET", customer_url(customer_id)).json()["postal_code"] == postal_code
    assert stored(crm, customer_id)["postal_code"] == postal_code


def test_k02_contrast_the_same_postal_code_with_poland_is_refused(crm: Crm) -> None:
    assert refused_at(crm, {"name": NAME, "country": "PL", "postal_code": "00950"}) == [
        ("postal_code",)
    ]


@pytest.mark.parametrize(
    ("sent", "located"),
    [
        pytest.param(REGION, [("voivodeship",), ("county",)], id="both"),
        pytest.param({"voivodeship": "mazowieckie"}, [("voivodeship",)], id="voivodeship"),
        pytest.param({"county": "warszawski zachodni"}, [("county",)], id="county"),
    ],
)
def test_k02_foreign_voivodeship_or_county_refused(
    crm: Crm, sent: dict[str, str], located: list[tuple[str]]
) -> None:
    assert refused_at(crm, {"name": NAME, "country": "DE", **sent}) == located


def test_k02_contrast_the_same_region_with_poland_is_stored(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "country": "PL", **REGION})
    row = stored(crm, customer_id)
    assert (row["voivodeship"], row["county"]) == ("mazowieckie", "warszawski zachodni")


def test_k02_a_foreign_customer_with_neither_voivodeship_nor_county_saves(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "country": "FR", "town": "Lyon"})
    row = stored(crm, customer_id)
    assert (row["voivodeship"], row["county"], row["town"]) == (None, None, "Lyon")


def test_k02_default_country_applies_polish_rules(crm: Crm) -> None:
    assert refused_at(crm, {"name": NAME, "postal_code": "00950"}) == [("postal_code",)]
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "postal_code": "00-950", **REGION})
    answer = rep.send("GET", customer_url(customer_id)).json()
    assert (answer["country"], answer["voivodeship"], answer["county"]) == (
        "PL",
        "mazowieckie",
        "warszawski zachodni",
    )
