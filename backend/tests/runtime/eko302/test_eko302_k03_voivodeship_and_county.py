"""EKO-3-02 K-03 (CUS-3; C-1 A, C-2 A; G-3 A, G-5 A; Q-4 A): for a Polish customer a given
voivodeship must be one of the 16 and a given county must belong to the chosen voivodeship, both
checked against the dated TERYT file in the repository; a county without a voivodeship is refused
at the county. Names cross the API exactly as the file writes them, keyed by (voivodeship, county).

The pairs are read from the file itself, not from the code under test. Synthetic customers only.
"""

import json
import unicodedata
from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create, created_id, customer_url
from tests.runtime.eko302.conftest import NAME, errors_at, stored
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

REGISTER = REPO_ROOT / "backend" / "app" / "domain" / "teryt_terc_2026-01-01.json"


def register_pairs() -> list[tuple[str, str]]:
    document = json.loads(REGISTER.read_text(encoding="utf-8"))
    return [(v["name"], c["name"]) for v in document["voivodeships"] for c in v["counties"]]


def twin_pairs() -> list[tuple[str, str]]:
    pairs = register_pairs()
    names = [county for _, county in pairs]
    return [(v, c) for v, c in pairs if names.count(c) > 1]


def refused_at(crm: Crm, body: dict[str, Any]) -> list[tuple[Any, ...]]:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    locations = errors_at(create(rep, {"name": NAME, "country": "PL", **body}))
    assert crm.counts() == before
    return locations


def accepted(crm: Crm, body: dict[str, Any]) -> dict[str, Any]:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "country": "PL", **body})
    return stored(crm, customer_id)


def test_k03_county_of_another_voivodeship_rejected(crm: Crm) -> None:
    row = accepted(crm, {"voivodeship": "podlaskie", "county": "bielski"})
    assert (row["voivodeship"], row["county"]) == ("podlaskie", "bielski")
    assert refused_at(crm, {"voivodeship": "mazowieckie", "county": "bielski"}) == [("county",)]


def test_k03_twin_county_names_each_with_own_voivodeship(crm: Crm) -> None:
    twins = twin_pairs()
    assert ("podlaskie", "bielski") in twins and ("śląskie", "bielski") in twins
    assert len(twins) >= 14
    for voivodeship, county in twins:
        row = accepted(crm, {"voivodeship": voivodeship, "county": county})
        assert (row["voivodeship"], row["county"]) == (voivodeship, county)


def test_k03_every_pair_of_the_register_is_accepted(crm: Crm) -> None:
    pairs = register_pairs()
    assert len(pairs) == 380
    rep = crm.login(REP_A, ["rep"])
    for voivodeship, county in pairs:
        made = create(
            rep, {"name": NAME, "country": "PL", "voivodeship": voivodeship, "county": county}
        )
        assert made.status_code == 201, (voivodeship, county, made.text)
    assert crm.counts()["customer"] == 380


def test_k03_county_without_voivodeship_rejected(crm: Crm) -> None:
    assert refused_at(crm, {"county": "bielski"}) == [("county",)]
    assert refused_at(crm, {"voivodeship": None, "county": "bielski"}) == [("county",)]
    assert refused_at(crm, {"voivodeship": "  ", "county": "bielski"}) == [("county",)]


def test_k03_both_omitted_saves(crm: Crm) -> None:
    row = accepted(crm, {"town": "Białystok"})
    assert (row["voivodeship"], row["county"]) == (None, None)


def test_k03_a_voivodeship_without_a_county_is_accepted(crm: Crm) -> None:
    row = accepted(crm, {"voivodeship": "zachodniopomorskie"})
    assert (row["voivodeship"], row["county"]) == ("zachodniopomorskie", None)


@pytest.mark.parametrize(
    "voivodeship",
    ["Podlaskie", "PODLASKIE", " podlaskie", "podlaskie ", "woj. podlaskie", "podlaskie\t"],
)
def test_k03_only_the_exact_voivodeship_counts(crm: Crm, voivodeship: str) -> None:
    assert refused_at(crm, {"voivodeship": voivodeship}) == [("voivodeship",)]


@pytest.mark.parametrize("county", ["Bielski", "BIELSKI", " bielski", "bielski ", "powiat bielski"])
def test_k03_only_the_exact_county_counts(crm: Crm, county: str) -> None:
    assert refused_at(crm, {"voivodeship": "podlaskie", "county": county}) == [("county",)]


def test_k03_nfd_and_nfc_are_the_same_value(crm: Crm) -> None:
    voivodeship = unicodedata.normalize("NFD", "śląskie")
    county = unicodedata.normalize("NFD", "bieruńsko-lędziński")
    assert voivodeship != "śląskie", "the edge would pass vacuously"
    row = accepted(crm, {"voivodeship": voivodeship, "county": county})
    assert (row["voivodeship"], row["county"]) == ("śląskie", "bieruńsko-lędziński")


def test_k03_a_city_with_county_rights_is_accepted(crm: Crm) -> None:
    row = accepted(crm, {"voivodeship": "mazowieckie", "county": "Warszawa"})
    assert row["county"] == "Warszawa"


def test_k03_an_unknown_county_with_a_valid_voivodeship_is_rejected(crm: Crm) -> None:
    assert refused_at(crm, {"voivodeship": "podlaskie", "county": "nieistniejący"}) == [("county",)]


def test_k03_an_invalid_voivodeship_with_a_county_gives_only_the_voivodeship_error(
    crm: Crm,
) -> None:
    assert refused_at(crm, {"voivodeship": "nadwiślańskie", "county": "bielski"}) == [
        ("voivodeship",)
    ]
    assert refused_at(crm, {"voivodeship": "nadwiślańskie", "county": "nieistniejący"}) == [
        ("voivodeship",)
    ]


def test_k03_the_order_of_keys_in_the_body_does_not_change_the_result(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    reversed_body = {"county": "bielski", "voivodeship": "śląskie", "country": "PL", "name": NAME}
    customer_id = created_id(rep, reversed_body)
    read = rep.send("GET", customer_url(customer_id)).json()
    assert (read["voivodeship"], read["county"]) == ("śląskie", "bielski")
    wrong = {"county": "bielski", "voivodeship": "mazowieckie", "country": "PL", "name": NAME}
    assert errors_at(create(rep, wrong)) == [("county",)]
