"""EKO-3-02 K-01 (CUS-1, CUS-2; G-1 A, G-2 A): a customer holds an optional street and number,
postal code, town, voivodeship, county and tax ID; each given value comes back from the create
answer and the by-id read, and a customer with only a name and a country still saves with every
new field not given. Bounds (trimmed NFC): street 150, town 100, foreign postal code 20, foreign
tax ID 32; each raw value is capped at four times its bound before trimming and NFC.

Sent straight to the API by a rep's real session, never through the SPA. Synthetic values only.
"""

import unicodedata
import uuid
from typing import Any

import httpx
import pytest

from tests.runtime.eko301.conftest import (
    MANAGER,
    REP_A,
    REP_B,
    Crm,
    create,
    created_id,
    customer_url,
)
from tests.runtime.eko302.conftest import NAME, NEW_FIELDS, errors_at, new_fields, stored
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

STREET_LIMIT = 150
TOWN_LIMIT = 100
FOREIGN_POSTAL_CODE_LIMIT = 20
FOREIGN_TAX_ID_LIMIT = 32
RAW_FACTOR = 4
NOTHING = {name: None for name in NEW_FIELDS}
CORRELATION = "eko-correlation-id"


def polish_body() -> dict[str, Any]:
    return {
        "name": NAME,
        "country": "PL",
        "street": "ul. Piotrkowska 104/2",
        "postal_code": "90-001",
        "town": "Łódź",
        "voivodeship": "łódzkie",
        "county": "Łódź",
        "tax_id": nips.valid_nip(1001),
    }


def foreign_body() -> dict[str, Any]:
    return {
        "name": NAME,
        "country": "DE",
        "street": "Hauptstraße 5",
        "postal_code": "10115",
        "town": "Berlin",
        "tax_id": "DE 12 3456 789",
    }


def read(browser: Any, customer_id: str) -> dict[str, Any]:
    response = browser.send("GET", customer_url(customer_id))
    assert response.status_code == 200, response.text
    answer: dict[str, Any] = response.json()
    return answer


@pytest.mark.parametrize("country", ["PL", "DE"])
def test_k01_name_and_country_only_still_saves(crm: Crm, country: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    made = create(rep, {"name": NAME, "country": country})
    assert made.status_code == 201, made.text
    assert new_fields(made.json()) == NOTHING
    assert new_fields(read(rep, made.json()["id"])) == NOTHING
    assert set(stored(crm, made.json()["id"]).values()) == {None}


def test_k01_every_new_field_reads_back(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    polish = polish_body()
    made = create(rep, polish)
    assert made.status_code == 201, made.text
    expected = {name: polish[name] for name in NEW_FIELDS}
    assert new_fields(made.json()) == expected
    assert new_fields(read(rep, made.json()["id"])) == expected
    row = stored(crm, made.json()["id"])
    assert (row["nip"], row["foreign_tax_id"]) == (polish["tax_id"], None)
    assert row["county"] == "Łódź" and row["voivodeship"] == "łódzkie"


def test_k01_a_foreign_customer_reads_back_with_its_tax_id_in_the_foreign_column(
    crm: Crm,
) -> None:
    rep = crm.login(REP_A, ["rep"])
    foreign = foreign_body()
    customer_id = created_id(rep, foreign)
    expected = {**NOTHING, **{k: foreign[k] for k in NEW_FIELDS if k in foreign}}
    assert new_fields(read(rep, customer_id)) == expected
    row = stored(crm, customer_id)
    assert (row["nip"], row["foreign_tax_id"]) == (None, "DE 12 3456 789")


BOUNDS = {
    "street": ("PL", STREET_LIMIT),
    "town": ("PL", TOWN_LIMIT),
    "postal_code": ("DE", FOREIGN_POSTAL_CODE_LIMIT),
    "tax_id": ("DE", FOREIGN_TAX_ID_LIMIT),
}


@pytest.mark.parametrize("field", sorted(BOUNDS))
def test_k01_bounds_and_one_past(crm: Crm, field: str) -> None:
    country, limit = BOUNDS[field]
    rep = crm.login(REP_A, ["rep"])
    at_limit = "K" * limit
    customer_id = created_id(rep, {"name": NAME, "country": country, field: at_limit})
    assert read(rep, customer_id)[field] == at_limit
    before = crm.counts()
    past = create(rep, {"name": NAME, "country": country, field: "K" * (limit + 1)})
    assert errors_at(past) == [(field,)]
    assert crm.counts() == before


@pytest.mark.parametrize("field", sorted(BOUNDS))
def test_k01_the_raw_cap_is_checked_before_trimming(crm: Crm, field: str) -> None:
    country, limit = BOUNDS[field]
    rep = crm.login(REP_A, ["rep"])
    cap = RAW_FACTOR * limit
    # One character trimmed to a valid value: accepted at the cap, refused one past it.
    padding = " " * (cap - 1)
    customer_id = created_id(rep, {"name": NAME, "country": country, field: "K" + padding})
    assert read(rep, customer_id)[field] == "K"
    before = crm.counts()
    past = create(rep, {"name": NAME, "country": country, field: "K" + padding + " "})
    assert errors_at(past) == [(field,)]
    assert crm.counts() == before


NOT_GIVEN: dict[str, Any] = {"null": None, "empty": "", "whitespace": " \t\n "}


# DE x voivodeship/county is K-02's C-3 refusal: test_eko302_assumptions.py::test_a10_* (A-07).
COUNTRY_FIELDS = [
    pytest.param(country, field, id=f"{country}-{field}")
    for country in ("PL", "DE")
    for field in NEW_FIELDS
    if not (country == "DE" and field in ("voivodeship", "county"))
]


@pytest.mark.parametrize("variant", ["omitted", *sorted(NOT_GIVEN)])
@pytest.mark.parametrize(("country", "field"), COUNTRY_FIELDS)
def test_k01_omitted_null_empty_and_whitespace_read_back_as_not_given(
    crm: Crm, field: str, variant: str, country: str
) -> None:
    rep = crm.login(REP_A, ["rep"])
    body: dict[str, Any] = {"name": NAME, "country": country}
    if variant != "omitted":
        body[field] = NOT_GIVEN[variant]
    customer_id = created_id(rep, body)
    assert read(rep, customer_id)[field] is None
    assert set(stored(crm, customer_id).values()) == {None}


def test_k01_text_is_trimmed_stored_as_nfc_and_counted_on_nfc(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    decomposed_town = unicodedata.normalize("NFD", "Łódź")
    assert decomposed_town != "Łódź", "the edge would pass vacuously"
    customer_id = created_id(
        rep, {"name": NAME, "street": "  ul. Polna 1  ", "town": decomposed_town}
    )
    answer = read(rep, customer_id)
    assert (answer["street"], answer["town"]) == ("ul. Polna 1", "Łódź")
    row = stored(crm, customer_id)
    assert [ord(c) for c in row["town"]] == [ord(c) for c in "Łódź"]
    # 101 code points as sent, 100 once composed: within the town's bound.
    long_town = "K" * (TOWN_LIMIT - 1) + "ó"
    assert len(long_town) == TOWN_LIMIT + 1
    customer_id = created_id(rep, {"name": NAME, "town": long_town})
    assert read(rep, customer_id)["town"] == "K" * (TOWN_LIMIT - 1) + "ó"


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b'{"name": "Gospodarstwo", "street": "ul. Polna \\u0000"}', id="nul-street"),
        pytest.param(b'{"name": "Gospodarstwo", "town": "Wie\\ud800"}', id="surrogate-town"),
        pytest.param(
            b'{"name": "Gospodarstwo", "country": "DE", "postal_code": "1\\udc00"}',
            id="surrogate-foreign-postal-code",
        ),
        pytest.param(
            b'{"name": "Gospodarstwo", "country": "DE", "tax_id": "DE\\u0000"}',
            id="nul-foreign-tax-id",
        ),
    ],
)
def test_k01_text_that_cannot_be_stored_is_refused(crm: Crm, content: bytes) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = rep.send(
        "POST", "/api/customers", content=content, headers={"content-type": "application/json"}
    )
    [located] = errors_at(response)
    assert located[0] in NEW_FIELDS
    assert crm.counts() == before


def test_k01_markup_in_the_street_is_stored_as_text(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    street = '<b>ul. Polna</b> <script>alert("1")</script>'
    customer_id = created_id(rep, {"name": NAME, "street": street})
    assert read(rep, customer_id)["street"] == street
    assert stored(crm, customer_id)["street"] == street


def test_k01_the_largest_valid_body_is_accepted_under_the_body_limit(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    contacts: list[dict[str, Any]] = [
        {
            "kind": "email",
            "value": f"k{index:02d}" + "x" * 239 + "@example.com",
            "note": "N" * 500,
            "primary": index == 0,
        }
        for index in range(50)
    ]
    body: dict[str, Any] = {
        "name": "G" * 120,
        "country": "PL",
        "street": "S" * STREET_LIMIT,
        "postal_code": "00-950",
        "town": "T" * TOWN_LIMIT,
        "voivodeship": "zachodniopomorskie",
        "county": "kołobrzeski",
        "tax_id": "PL " + nips.spaced(nips.valid_nip(2002)) + " " * 16,
        "contacts": contacts,
    }
    assert len(contacts[0]["value"]) == 254
    assert len(body["tax_id"]) == 32
    made = create(rep, body)
    assert made.status_code == 201, made.text[:300]
    assert len(made.request.content) < 2 * 1024 * 1024
    assert crm.counts() == {"customer_contact": 50, "customer": 1}


def answer_of(response: httpx.Response) -> tuple[int, bytes, list[tuple[str, str]]]:
    headers = sorted((k.lower(), v) for k, v in response.headers.multi_items())
    return response.status_code, response.content, [h for h in headers if h[0] != CORRELATION]


def test_k01_another_reps_customer_with_an_address_reads_as_one_that_exists_nowhere(
    crm: Crm,
) -> None:
    owned = created_id(crm.login(REP_A, ["rep"]), polish_body())
    rep_b = crm.login(REP_B, ["rep"])
    denied = rep_b.send("GET", customer_url(owned))
    missing = rep_b.send("GET", customer_url(str(uuid.uuid4())))
    assert denied.status_code == 404, denied.text
    assert answer_of(denied) == answer_of(missing)
    for value in ("Piotrkowska", "90-001", "łódzkie", nips.valid_nip(1001)):
        assert value not in denied.text
    manager = crm.login(MANAGER, ["manager"])
    assert new_fields(read(manager, owned)) == {k: polish_body()[k] for k in NEW_FIELDS}
