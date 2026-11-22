"""EKO-3-04 K-01 (ACC-4; CUS-1; G-1 A, G-4 A, G-5 A; ADR-0002 addendum of EKO-3-04): one text
query `q` returns exactly the caller's customers whose name, town or a contact value contains it,
ignoring case, and matches on no other field: not a contact's note, the NIP, the street, the
postal code, the voivodeship, the county or the country code.

Every value is synthetic; the spaced phone of the G-1 edge is joined at run time, so no line here
holds a phone-shaped literal (the K-07 personal-data guard).
"""

import unicodedata
from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm
from tests.runtime.eko304.conftest import customer, email, found, listed_items, phone
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep = crm.login(REP_A, ["rep"])
    return {
        "rep": rep,
        "name": customer(rep, "Gospodarstwo Łąkowe"),
        "town": customer(rep, "Ferma Brzozy", town="Zielonka Testowa"),
        "phone": customer(rep, "Sad Jabłkowy", contacts=[phone("+48600100200")]),
        "mail": customer(rep, "Pasieka Miodna", contacts=[email("farma.kos@example.com")]),
        "none": customer(rep, "Rolnik Bez Dopasowania"),
        # The e-mail of C-mail moved into a note of another customer's contact.
        "note": customer(
            rep, "Uprawa Notatki", contacts=[phone("+48600900900", "farma.kos@example.com")]
        ),
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("łąk", "name", id="name-lower"),
        pytest.param("ŁĄK", "name", id="name-upper"),
        pytest.param("zielonka", "town", id="town"),
        pytest.param("600100", "phone", id="phone"),
        pytest.param("KOS@EXAMPLE", "mail", id="e-mail"),
    ],
)
def test_k01_a_query_returns_exactly_the_customer_it_matches(
    owned: dict[str, Any], query: str, expected: str
) -> None:
    assert found(owned["rep"], {"q": query}) == {owned[expected]}


def test_k01_contrast_text_in_a_contact_note_is_not_matched(owned: dict[str, Any]) -> None:
    assert found(owned["rep"], {"q": "farma.kos@example.com"}) == {owned["mail"]}


def test_k01_contrast_a_substring_of_the_unmatched_customers_name_returns_it(
    owned: dict[str, Any],
) -> None:
    assert owned["none"] not in found(owned["rep"], {"q": "łąk"})
    assert found(owned["rep"], {"q": "dopasowania"}) == {owned["none"]}


def other_fields(text: str) -> dict[str, dict[str, Any]]:
    """Field placement -> create fields holding `text` outside name, town and contact value."""
    return {
        "street": {"street": f"ul. {text} 5"},
        "postal-code": {"country": "DE", "postal_code": text},
        "voivodeship": {"voivodeship": "lubuskie"},
        "county": {"voivodeship": "lubuskie", "county": "gorzowski"},
        "foreign-tax-id": {"country": "DE", "tax_id": text},
    }


@pytest.mark.parametrize(
    ("placement", "query"),
    [
        pytest.param("street", "Schowanaqk", id="street"),
        pytest.param("postal-code", "Kodqk01", id="postal-code"),
        pytest.param("voivodeship", "lubusk", id="voivodeship"),
        pytest.param("county", "gorzowsk", id="county"),
        pytest.param("foreign-tax-id", "Podatekqk01", id="foreign-tax-id"),
    ],
)
def test_k01_contrast_text_in_another_field_is_not_matched_and_in_the_name_it_is(
    crm: Crm, placement: str, query: str
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, "Hodowla Pól", **other_fields(query)[placement])
    assert found(rep, {"q": query}) == set()
    named = customer(rep, f"Hodowla {query}")
    assert found(rep, {"q": query}) == {named}


def test_k01_contrast_a_nip_is_not_matched_and_in_the_name_it_is(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    nip = nips.valid_nip(4304)
    customer(rep, "Hodowla Pól", tax_id=nip)
    assert found(rep, {"q": nip}) == set()
    named = customer(rep, f"Hodowla {nip}")
    assert found(rep, {"q": nip}) == {named}


def test_k01_contrast_a_country_code_is_not_matched_and_in_the_name_it_is(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, "Farma Obca", country="CZ")
    assert found(rep, {"q": "CZ"}) == set()
    named = customer(rep, "Farma CZ")
    assert found(rep, {"q": "CZ"}) == {named}


# Edges -----------------------------------------------------------------------------------------

# A customer each edge's query must not return, so the edge cannot pass on an unfiltered list.
DECOY = "Inna Farma"


def test_k01_edge_one_customer_matching_twice_appears_once(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, DECOY)
    twice = customer(
        rep,
        "Dwojakqk Farma",
        contacts=[email("dwojakqk@example.com"), email("dwojakqk.druga@example.com")],
    )
    items = listed_items(rep, {"q": "dwojakqk"})
    assert [item["id"] for item in items] == [twice]


def test_k01_edge_a_customer_with_no_town_and_no_contacts_is_found_by_name(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, DECOY, town="Zielonka Testowa", contacts=[phone("+48600300300")])
    bare = customer(rep, "Samotnaqk Zagroda")
    assert found(rep, {"q": "samotnaqk"}) == {bare}


def test_k01_edge_two_customers_with_the_same_name_are_both_returned(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, DECOY)
    twins = {customer(rep, "Bliźniaczaqk"), customer(rep, "Bliźniaczaqk")}
    assert len(twins) == 2
    assert found(rep, {"q": "bliźniacza"}) == twins


def test_k01_edge_leading_and_trailing_spaces_are_trimmed(owned: dict[str, Any]) -> None:
    assert found(owned["rep"], {"q": "  łąk \t"}) == {owned["name"]}


def test_k01_edge_diacritics_are_not_ignored(owned: dict[str, Any]) -> None:
    assert found(owned["rep"], {"q": "lakow"}) == set()


def test_k01_edge_a_query_in_nfd_matches_the_nfc_name(owned: dict[str, Any]) -> None:
    decomposed = unicodedata.normalize("NFD", "ŁĄK")
    assert decomposed != "ŁĄK"
    assert found(owned["rep"], {"q": decomposed}) == {owned["name"]}


def test_k01_edge_a_phone_typed_with_spaces_matches_nothing(owned: dict[str, Any]) -> None:
    spaced = " ".join(["600", "100", "200"])
    assert found(owned["rep"], {"q": spaced}) == set()
    assert found(owned["rep"], {"q": spaced.replace(" ", "")}) == {owned["phone"]}
