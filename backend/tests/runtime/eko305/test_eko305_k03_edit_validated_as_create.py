"""EKO-3-05 K-03 (CUS-1 to CUS-5, CUS-8; Q-5, G-6 A; ADR-0005-C2): an edit is validated exactly as
a create. For each rule the same invalid input goes once to `POST /api/customers` and once to
`PUT /api/customers/{id}`, and the two 422 answers are equal, located at `["body", <field>]`. A
rejected edit leaves the stored customer and its contacts byte-identical, and repeats no submitted
value in its answer or in any log record the backend writes, at DEBUG.

Until EKO-3-03 a NIP edit is not checked for uniqueness: a valid NIP another customer holds is
accepted, and the answer says nothing a NIP nobody holds would not (ADR-0002 addendum of
EKO-3-02, a declared deviation; the release constraint "no real data before EKO-3-03" holds).
EKO-3-03 must change the pin below on purpose.
"""

import json
import logging
import unicodedata
from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, REP_B, Crm, create, customer_url
from tests.runtime.eko302.test_eko302_k05_rejected_stores_nothing_repeats_nothing import (
    logged_text,
)
from tests.runtime.eko305.conftest import (
    customer,
    edit,
    email,
    phone,
    read_json,
    snapshot,
    status_and_json,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

STORED: dict[str, Any] = {
    "name": "Gospodarstwo Walidacja K03",
    "street": "ul. Stała 3",
    "postal_code": "03-003",
    "voivodeship": "mazowieckie",
    "county": "Warszawa",
    "contacts": [phone("+48601305300", "Notatka K03", primary=True)],
}
NAME = "Gospodarstwo Edycja K03"


Rule = tuple[dict[str, Any], str, str, dict[str, Any]]


def rules() -> dict[str, Rule]:
    """rule case -> (the body, the field it is refused at, a submitted value that must not come
    back, the same body with only that field corrected). Only the named field fails."""
    wrong_nip = nips.wrong_check_digit(nips.valid_nip(305301))
    nip = nips.valid_nip(305301)
    two = [phone("+48601305391", primary=True), phone("+48601305392", primary=True)]
    return {
        "cus2-name-missing": ({"town": "Wola"}, "name", "", {"town": "Wola", "name": NAME}),
        "cus2-name-empty": ({"name": "   "}, "name", "", {"name": NAME}),
        "cus2-name-null": ({"name": None}, "name", "", {"name": NAME}),
        "cus2-country-null": (
            {"name": NAME, "country": None},
            "country",
            "",
            {"name": NAME, "country": "PL"},
        ),
        "cus2-country-outside-the-list": (
            {"name": NAME, "country": "XQ"},
            "country",
            "XQ",
            {"name": NAME, "country": "CZ"},
        ),
        "cus3-postal-code": (
            {"name": NAME, "postal_code": "3K-303"},
            "postal_code",
            "3K-303",
            {"name": NAME, "postal_code": "03-303"},
        ),
        "cus3-unknown-voivodeship": (
            {"name": NAME, "voivodeship": "znacznikowskie"},
            "voivodeship",
            "znacznikowskie",
            {"name": NAME, "voivodeship": "lubuskie"},
        ),
        "cus3-county-of-another-voivodeship": (
            {"name": NAME, "voivodeship": "mazowieckie", "county": "kołobrzeski"},
            "county",
            "kołobrzeski",
            {"name": NAME, "voivodeship": "mazowieckie", "county": "otwocki"},
        ),
        "cus3-county-without-voivodeship": (
            {"name": NAME, "county": "gołdapski"},
            "county",
            "gołdapski",
            {"name": NAME, "county": None},
        ),
        "cus4-foreign-voivodeship": (
            {"name": NAME, "country": "DE", "voivodeship": "pomorskie"},
            "voivodeship",
            "pomorskie",
            {"name": NAME, "country": "DE", "voivodeship": None},
        ),
        "cus4-foreign-county": (
            {"name": NAME, "country": "DE", "county": "lęborski"},
            "county",
            "lęborski",
            {"name": NAME, "country": "DE", "county": ""},
        ),
        "cus5-nip-checksum": (
            {"name": NAME, "tax_id": nips.hyphenated(wrong_nip)},
            "tax_id",
            wrong_nip,
            {"name": NAME, "tax_id": nips.hyphenated(nip)},
        ),
        "cus8-email": (
            {"name": NAME, "contacts": [email("znacznik-k03@@farm")]},
            "contacts",
            "znacznik-k03@@farm",
            {"name": NAME, "contacts": [email("znacznik-k03@farm.example.invalid")]},
        ),
        "cus8-phone": (
            {"name": NAME, "contacts": [phone("0123-K03-ZNACZNIK")]},
            "contacts",
            "0123-K03-ZNACZNIK",
            {"name": NAME, "contacts": [phone("601305393")]},
        ),
        "cus1-two-primaries": (
            {"name": NAME, "contacts": two},
            "",
            "+48601305391",
            {"name": NAME, "contacts": [two[0], {**two[1], "primary": False}]},
        ),
    }


@pytest.fixture
def stored(crm: Crm) -> Iterator[tuple[Any, str]]:
    rep = crm.login(REP_A, ["rep"])
    yield rep, customer(rep, **STORED)


def located(response: Any) -> list[tuple[Any, ...]]:
    assert response.status_code == 422, response.text
    return [tuple(error["loc"][:2]) for error in response.json()["detail"]]


@pytest.mark.parametrize("case", sorted(rules()))
def test_k03_an_edit_is_refused_exactly_as_the_create_of_the_same_input(
    crm: Crm, stored: tuple[Any, str], caplog: pytest.LogCaptureFixture, case: str
) -> None:
    rep, customer_id = stored
    body, field, value, _ = rules()[case]
    before = snapshot(crm)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    edited = edit(rep, customer_id, body)
    created = create(rep, body)
    assert status_and_json(edited) == status_and_json(created)
    expected = ("body", field) if field else ("body",)
    assert expected in located(edited), edited.text
    assert snapshot(crm) == before
    assert caplog.records, "no log record at all: the capture would pass vacuously"
    if value:
        assert value not in edited.text
        assert value not in logged_text(caplog.records)


@pytest.mark.parametrize("case", sorted(rules()))
def test_k03_contrast_the_same_edit_with_only_the_failing_field_corrected_is_stored(
    crm: Crm, stored: tuple[Any, str], case: str
) -> None:
    rep, customer_id = stored
    corrected = rules()[case][3]
    before = snapshot(crm)
    response = edit(rep, customer_id, corrected)
    assert response.status_code == 200, (case, response.text)
    assert snapshot(crm) != before


def test_k03_a_rejected_edit_touching_storage_rolls_its_contacts_back(crm: Crm) -> None:
    """K-03 M-i: the replacement contacts are written in the customer's transaction. A trigger
    planted for this test refuses one synthetic contact value, the last of three, so the edit
    fails in storage after the old contacts were deleted and the row was updated."""
    refused, accepted = "+48601305399", "+48601305398"
    plant = f"""
    CREATE FUNCTION qa_eko305_refuse_contact() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.value = '{refused}' THEN RAISE EXCEPTION 'planted refusal'; END IF;
        RETURN NEW;
    END
    $$;
    CREATE TRIGGER qa_eko305_refuse_contact BEFORE INSERT ON customer_contact
        FOR EACH ROW EXECUTE FUNCTION qa_eko305_refuse_contact();
    """
    remove = """
    DROP TRIGGER IF EXISTS qa_eko305_refuse_contact ON customer_contact;
    DROP FUNCTION IF EXISTS qa_eko305_refuse_contact();
    """
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)

    def body(last: str) -> dict[str, Any]:
        return {
            "name": NAME,
            "contacts": [
                phone("+48601305397", primary=True),
                email("transakcja-k03@farm.example.invalid"),
                phone(last),
            ],
        }

    with crm.pg.connect() as connection:
        connection.execute(remove)
        connection.execute(plant)
    try:
        before = snapshot(crm)
        response = edit(rep, customer_id, body(refused))
        assert response.status_code == 503, response.text
        assert snapshot(crm) == before
        # Contrast: only the last value differs, and the edit is stored with its three contacts.
        stored_edit = edit(rep, customer_id, body(accepted))
        assert stored_edit.status_code == 200, stored_edit.text
        assert len(read_json(rep, customer_id)["contacts"]) == 3
    finally:
        with crm.pg.connect() as connection:
            connection.execute(remove)


def test_k03_a_nip_another_customer_holds_is_accepted_and_answered_as_an_unused_one(
    crm: Crm,
) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    held_by_a = nips.valid_nip(305311)
    held_by_b = nips.valid_nip(305321)
    unused = nips.valid_nip(305331)
    customer(rep_a, "Sasiad A K03", tax_id=held_by_a)
    customer(rep_b, "Sasiad B K03", tax_id=held_by_b)
    target = customer(rep_a, "Cel K03")

    def edited_with(nip: str) -> dict[str, Any]:
        response = edit(rep_a, target, {"name": "Cel K03", "tax_id": nips.spaced(nip)})
        assert response.status_code == 200, response.text
        answered: dict[str, Any] = response.json()
        assert answered["tax_id"] == nip
        return {**answered, "tax_id": None}

    baseline = edited_with(unused)
    assert edited_with(held_by_a) == baseline
    assert edited_with(held_by_b) == baseline
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE nip = %s", (held_by_b,)) == [(2,)]
    # Contrast: the same NIP with one check digit changed is refused.
    wrong = edit(rep_a, target, {"name": "Cel K03", "tax_id": nips.wrong_check_digit(held_by_b)})
    assert located(wrong) == [("body", "tax_id")]


DECOMPOSED = unicodedata.normalize("NFD", "Zażółć Gęślą Jaźń")


def test_k03_edge_text_is_trimmed_normalised_and_markup_is_stored_as_text(
    crm: Crm, stored: tuple[Any, str]
) -> None:
    rep, customer_id = stored
    body = {"name": f"  <b>{DECOMPOSED}</b> ", "town": f" {DECOMPOSED} "}
    created = create(rep, body).json()
    edited = edit(rep, customer_id, body)
    assert edited.status_code == 200, edited.text
    record = read_json(rep, customer_id)
    assert (record["name"], record["town"]) == (created["name"], created["town"])
    assert record["name"] == "<b>" + unicodedata.normalize("NFC", DECOMPOSED) + "</b>"


@pytest.mark.parametrize(
    ("body", "accepted"),
    [
        pytest.param({"name": "N" * 120}, True, id="name-at-limit"),
        pytest.param({"name": "N" * 121}, False, id="name-past-limit"),
        pytest.param(
            {"name": "N", "contacts": [phone(f"+4860130{i:04d}") for i in range(50)]},
            True,
            id="50-contacts",
        ),
        pytest.param(
            {"name": "N", "contacts": [phone(f"+4860130{i:04d}") for i in range(51)]},
            False,
            id="51-contacts",
        ),
        pytest.param({}, False, id="empty-body"),
        pytest.param(
            {"name": "N", "country": "DE", "voivodeship": "mazowieckie"},
            False,
            id="pl-to-foreign-with-voivodeship",
        ),
    ],
)
def test_k03_edge_bounds_and_body_alone_answer_as_create(
    crm: Crm, stored: tuple[Any, str], body: dict[str, Any], accepted: bool
) -> None:
    rep, customer_id = stored
    before = snapshot(crm)
    edited = edit(rep, customer_id, body)
    created = create(rep, body)
    assert (edited.status_code == 200, created.status_code == 201) == (accepted, accepted)
    if not accepted:
        assert status_and_json(edited) == status_and_json(created)
        assert snapshot(crm) == before


LIMIT = 2 * 1024 * 1024


def padded(body: dict[str, Any], size: int) -> bytes:
    encoded = json.dumps(body).encode("ascii")
    assert len(encoded) <= size
    return encoded + b" " * (size - len(encoded))


def test_k03_edge_an_edit_body_at_the_limit_is_judged_and_one_byte_more_is_413(
    crm: Crm, stored: tuple[Any, str]
) -> None:
    rep, customer_id = stored
    headers = {"content-type": "application/json"}
    url = customer_url(customer_id)
    at_limit = rep.send("PUT", url, content=padded({"name": NAME}, LIMIT), headers=headers)
    assert at_limit.status_code == 200, at_limit.text[:300]
    before = snapshot(crm)
    past = rep.send("PUT", url, content=padded({"name": "Za Duze"}, LIMIT + 1), headers=headers)
    assert status_and_json(past) == (413, {"detail": "request body too large"})
    assert snapshot(crm) == before
