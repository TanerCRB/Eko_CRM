"""EKO-3-01 K-02 (CUS-1; G-4 A, G-5 A, G-6 A): a customer holds any number of phones and e-mails,
each with an optional note stored as the NFC of the input, kept in the order sent; at most one
contact is primary, counted across kinds; one past each bound is rejected and stores nothing.
"""

import unicodedata
from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create, created_id, customer_url, listed_ids

pytestmark = pytest.mark.runtime

CONTACT_LIMIT = 50
NOTE_LIMIT = 500
DECOMPOSED_NOTE = "Pani Zo\u0301\u0142, ksie\u0328gowa"


def phone(value: Any, note: Any = None, primary: bool = False) -> dict[str, Any]:
    return {"kind": "phone", "value": value, "note": note, "primary": primary}


def email(value: Any, note: Any = None, primary: bool = False) -> dict[str, Any]:
    return {"kind": "email", "value": value, "note": note, "primary": primary}


FIVE = [
    phone("+48601000001", note="Owner, mornings", primary=True),
    phone("+48601000002"),
    phone("+48601000003", note="Farm office"),
    email("biuro@farm01.example.invalid", note="Accounts"),
    email("owner@farm01.example.invalid"),
]


def stored_contacts(crm: Crm, customer_id: str) -> list[tuple[Any, ...]]:
    """The contact rows as PostgreSQL holds them, in their stored order."""
    return crm.pg.rows(
        "SELECT kind, value, note, is_primary FROM customer_contact WHERE customer_id = %s "
        "ORDER BY position",
        (customer_id,),
    )


def read_contacts(crm: Crm, browser: Any, customer_id: str) -> list[dict[str, Any]]:
    response = browser.send("GET", customer_url(customer_id))
    assert response.status_code == 200, response.text
    contacts: list[dict[str, Any]] = response.json()["contacts"]
    return contacts


def as_read(contact: dict[str, Any]) -> dict[str, Any]:
    return {**contact, "note": contact["note"] or None}


def test_k02_three_phones_and_two_emails_read_back_with_notes_and_one_primary(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": "Gospodarstwo Kontakty 01", "contacts": FIVE})
    assert read_contacts(crm, rep, customer_id) == [as_read(c) for c in FIVE]
    assert stored_contacts(crm, customer_id) == [
        (c["kind"], c["value"], c["note"], c["primary"]) for c in FIVE
    ]


def test_k02_contrast_a_second_primary_is_rejected_and_nothing_is_stored(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    created_id(rep, {"name": "Gospodarstwo Kontakty 02"})
    before_list, before_counts = listed_ids(rep), crm.counts()
    two_primaries = [*FIVE[:1], phone("+48601000002", primary=True), *FIVE[2:]]
    response = create(rep, {"name": "Gospodarstwo Kontakty 03", "contacts": two_primaries})
    assert response.status_code == 422, response.text
    assert listed_ids(rep) == before_list
    assert crm.counts() == before_counts


def test_k02_a_primary_phone_and_a_primary_email_count_as_two(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    body = {
        "name": "Gospodarstwo Kontakty 04",
        "contacts": [
            phone("+48601000004", primary=True),
            email("a@farm04.example.invalid", primary=True),
        ],
    }
    assert create(rep, body).status_code == 422
    assert crm.counts() == before


@pytest.mark.parametrize(
    "contacts",
    [
        pytest.param(None, id="omitted"),
        pytest.param([], id="empty-list"),
    ],
)
def test_k02_no_contacts_saves_a_customer_without_contacts(crm: Crm, contacts: Any) -> None:
    rep = crm.login(REP_A, ["rep"])
    body: dict[str, Any] = {"name": "Gospodarstwo Kontakty 05"}
    if contacts is not None:
        body["contacts"] = contacts
    customer_id = created_id(rep, body)
    assert read_contacts(crm, rep, customer_id) == []
    assert stored_contacts(crm, customer_id) == []


@pytest.mark.parametrize(
    "contacts",
    [
        pytest.param([phone("+48601000006", primary=True)], id="one-primary"),
        pytest.param([email("one@farm06.example.invalid")], id="one-not-primary"),
        pytest.param([phone("+48601000006"), email("x@farm06.example.invalid")], id="none-primary"),
    ],
)
def test_k02_one_contact_or_none_primary_is_accepted(crm: Crm, contacts: list[Any]) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": "Gospodarstwo Kontakty 06", "contacts": contacts})
    assert read_contacts(crm, rep, customer_id) == [as_read(c) for c in contacts]


@pytest.mark.parametrize("note", [pytest.param(None, id="null"), pytest.param("", id="empty")])
def test_k02_a_null_or_empty_note_means_no_note(crm: Crm, note: Any) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(
        rep, {"name": "Gospodarstwo Kontakty 07", "contacts": [phone("+48601000007", note=note)]}
    )
    assert read_contacts(crm, rep, customer_id)[0]["note"] is None
    assert stored_contacts(crm, customer_id)[0][2] is None


def test_k02_an_omitted_note_means_no_note(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    contact = {"kind": "phone", "value": "+48601000008", "primary": False}
    customer_id = created_id(rep, {"name": "Gospodarstwo Kontakty 08", "contacts": [contact]})
    assert stored_contacts(crm, customer_id) == [("phone", "+48601000008", None, False)]


def test_k02_a_decomposed_note_is_stored_composed(crm: Crm) -> None:
    expected = unicodedata.normalize("NFC", DECOMPOSED_NOTE)
    assert [ord(c) for c in DECOMPOSED_NOTE] != [ord(c) for c in expected], "vacuous edge"
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(
        rep,
        {
            "name": "Gospodarstwo Kontakty 09",
            "contacts": [phone("+48601000009", note=DECOMPOSED_NOTE)],
        },
    )
    read = read_contacts(crm, rep, customer_id)[0]["note"]
    assert [ord(c) for c in read] == [ord(c) for c in expected]
    stored = stored_contacts(crm, customer_id)[0][2]
    assert [ord(c) for c in stored] == [ord(c) for c in expected]


def test_k02_a_note_with_markup_is_stored_as_sent(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(
        rep,
        {"name": "Gospodarstwo Kontakty 10", "contacts": [phone("+48601000010", note="<b>x</b>")]},
    )
    assert stored_contacts(crm, customer_id)[0][2] == "<b>x</b>"
    assert read_contacts(crm, rep, customer_id)[0]["note"] == "<b>x</b>"


def test_k02_twenty_phones_and_twenty_emails_are_all_kept_in_order(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    contacts = [phone(f"+4860100{n:04d}") for n in range(20)] + [
        email(f"c{n}@farm11.example.invalid") for n in range(20)
    ]
    customer_id = created_id(rep, {"name": "Gospodarstwo Kontakty 11", "contacts": contacts})
    assert [c["value"] for c in read_contacts(crm, rep, customer_id)] == [
        c["value"] for c in contacts
    ]


def test_k02_the_contact_bound_and_one_past_it(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    at_limit = [phone(f"+4860200{n:04d}") for n in range(CONTACT_LIMIT)]
    customer_id = created_id(rep, {"name": "Gospodarstwo Kontakty 12", "contacts": at_limit})
    assert len(stored_contacts(crm, customer_id)) == CONTACT_LIMIT
    before = crm.counts()
    past = [*at_limit, phone("+48602999999")]
    assert create(rep, {"name": "Gospodarstwo Kontakty 13", "contacts": past}).status_code == 422
    assert crm.counts() == before


def test_k02_the_note_bound_is_counted_on_the_nfc_form(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    too_long = [phone("+48601000014", note="n" * (NOTE_LIMIT + 1))]
    assert (
        create(rep, {"name": "Gospodarstwo Kontakty 14", "contacts": too_long}).status_code == 422
    )
    assert crm.counts() == before
    at_limit = [phone("+48601000015", note="n" * NOTE_LIMIT)]
    assert (
        create(rep, {"name": "Gospodarstwo Kontakty 15", "contacts": at_limit}).status_code == 201
    )
    # 501 code points as sent, 500 once composed.
    decomposed = "n" * (NOTE_LIMIT - 1) + "o\u0301"
    assert len(unicodedata.normalize("NFC", decomposed)) == NOTE_LIMIT
    customer_id = created_id(
        rep,
        {"name": "Gospodarstwo Kontakty 16", "contacts": [phone("+48601000016", note=decomposed)]},
    )
    assert stored_contacts(crm, customer_id)[0][2] == "n" * (NOTE_LIMIT - 1) + "\u00f3"


@pytest.mark.parametrize(
    "contact",
    [
        pytest.param(phone(""), id="empty-phone"),
        pytest.param(email(""), id="empty-email"),
        pytest.param(email("   "), id="spaces-email"),
        pytest.param({"kind": "phone", "note": None, "primary": False}, id="value-omitted"),
        pytest.param(phone(None), id="value-null"),
    ],
)
def test_k02_a_contact_with_an_empty_value_is_rejected(crm: Crm, contact: Any) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    body = {"name": "Gospodarstwo Kontakty 17", "contacts": [phone("+48601000017"), contact]}
    assert create(rep, body).status_code == 422
    assert crm.counts() == before


def test_k02_two_identical_values_on_one_customer_are_accepted(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    twins = [phone("+48601000018", note="first"), phone("+48601000018", note="second")]
    customer_id = created_id(rep, {"name": "Gospodarstwo Kontakty 18", "contacts": twins})
    assert stored_contacts(crm, customer_id) == [
        ("phone", "+48601000018", "first", False),
        ("phone", "+48601000018", "second", False),
    ]
