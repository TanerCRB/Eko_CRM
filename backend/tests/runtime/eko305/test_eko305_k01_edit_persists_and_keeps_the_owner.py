"""EKO-3-05 K-01 (ACC-4, ACC-5; G-5 A, G-6 A, Q-3 A, Q-5; ADR-0003-C39, success half): the owner or
the manager edits a customer with `PUT /api/customers/{id}`; the change is stored, a separate read
shows exactly the values sent, and the owner stays the stored one.

An edit states the whole customer under the create body rules: a stored value omitted from the
body, or sent as `null` or `""`, reads back `null`; omitted contacts read back as none; an omitted
country reads back `PL`. A body naming an owner is refused `extra_forbidden` and changes nothing.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import (
    ADMINISTRATOR,
    MANAGER,
    REP_A,
    REP_AND_MANAGER,
    Crm,
)
from tests.runtime.eko305.conftest import (
    NOT_PERMITTED,
    customer,
    edit,
    email,
    found,
    phone,
    read_json,
    snapshot,
    status_and_json,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

STORED: dict[str, Any] = {
    "name": "Gospodarstwo Przed Edycja",
    "street": "ul. Stara 1",
    "postal_code": "00-001",
    "town": "Stare Miasto",
    "voivodeship": "mazowieckie",
    "county": "Warszawa",
    "contacts": [phone("+48601305001", "Stara notatka", primary=True)],
}


def edited_body() -> dict[str, Any]:
    nip = nips.valid_nip(305001)
    return {
        "name": "Gospodarstwo Po Edycji",
        "country": "PL",
        "street": "ul. Nowa 2",
        "postal_code": "02-002",
        "town": "Nowe Miasto",
        "voivodeship": "pomorskie",
        "county": "lęborski",
        "tax_id": nips.hyphenated(nip),
        "contacts": [
            email("nowa-edycja@farm.example.invalid", "Biuro"),
            phone("601305002", primary=True),
        ],
    }


def expected_record(customer_id: str) -> dict[str, Any]:
    return {
        "id": customer_id,
        "name": "Gospodarstwo Po Edycji",
        "country": "PL",
        "street": "ul. Nowa 2",
        "postal_code": "02-002",
        "town": "Nowe Miasto",
        "voivodeship": "pomorskie",
        "county": "lęborski",
        "tax_id": nips.valid_nip(305001),
        "contacts": [
            {
                "kind": "email",
                "value": "nowa-edycja@farm.example.invalid",
                "note": "Biuro",
                "primary": False,
            },
            {"kind": "phone", "value": "+48601305002", "note": None, "primary": True},
        ],
        "archived": False,
    }


def owner_of(crm: Crm, customer_id: str) -> str:
    [(owner,)] = crm.pg.rows("SELECT owner_subject FROM customer WHERE id = %s", (customer_id,))
    return str(owner)


def test_k01_a_rep_edits_their_own_customer_and_a_separate_read_shows_exactly_the_sent_values(
    crm: Crm,
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)
    response = edit(rep, customer_id, edited_body())
    assert response.status_code == 200, response.text
    assert response.json() == expected_record(customer_id)
    assert response.headers.get_list("cache-control") == ["no-store"]
    # The PUT's own answer is not trusted alone: a separate read returns the stored values.
    assert read_json(rep, customer_id) == expected_record(customer_id)
    assert owner_of(crm, customer_id) == REP_A


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(MANAGER, ["manager"], id="manager-without-rep"),
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
    ],
)
def test_k01_the_manager_edits_a_reps_customer_and_the_customer_stays_the_reps(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)
    manager = crm.login(subject, roles)
    response = edit(manager, customer_id, edited_body())
    assert response.status_code == 200, response.text
    assert "owner" not in response.json() and "owner_subject" not in response.json()
    assert owner_of(crm, customer_id) == REP_A
    assert read_json(rep, customer_id) == expected_record(customer_id)
    assert customer_id in found(rep)
    assert customer_id in found(manager, {"owner": REP_A})
    assert customer_id not in found(manager, {"owner": subject})


@pytest.mark.parametrize("key", ["owner", "owner_subject"])
def test_k01_a_body_naming_an_owner_is_refused_and_the_customer_is_unchanged(
    crm: Crm, key: str
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)
    manager = crm.login(MANAGER, ["manager"])
    before = snapshot(crm)
    refused = edit(manager, customer_id, {**edited_body(), key: MANAGER})
    assert refused.status_code == 422, refused.text
    assert [(e["type"], e["loc"]) for e in refused.json()["detail"]] == [
        ("extra_forbidden", ["body", key])
    ]
    assert snapshot(crm) == before
    # Contrast: only the key differs, and the same edit succeeds.
    accepted = edit(manager, customer_id, edited_body())
    assert accepted.status_code == 200, accepted.text
    assert owner_of(crm, customer_id) == REP_A


def test_k01_contrast_an_administrator_only_account_gets_403_and_nothing_changes(
    crm: Crm,
) -> None:
    customer_id = customer(crm.login(REP_A, ["rep"]), **STORED)
    administrator = crm.login(ADMINISTRATOR, ["administrator"])
    before = snapshot(crm)
    assert status_and_json(edit(administrator, customer_id, edited_body())) == NOT_PERMITTED
    assert snapshot(crm) == before


OPTIONAL_FIELDS = ("street", "postal_code", "town", "voivodeship", "county", "tax_id")
NOT_GIVEN = {"omitted": ..., "null": None, "empty": ""}


@pytest.mark.parametrize("field", OPTIONAL_FIELDS)
@pytest.mark.parametrize("form", sorted(NOT_GIVEN))
def test_k01_a_stored_field_omitted_null_or_empty_in_the_edit_reads_back_null(
    crm: Crm, field: str, form: str
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **{**edited_body(), "name": "Gospodarstwo Pelne"})
    assert read_json(rep, customer_id)[field] is not None
    body = edited_body()
    # A county is judged with its voivodeship, so clearing the voivodeship clears both.
    cleared = {field, "county"} if field == "voivodeship" else {field}
    for name in cleared:
        if NOT_GIVEN[form] is ...:
            body.pop(name)
        else:
            body[name] = NOT_GIVEN[form]
    response = edit(rep, customer_id, body)
    assert response.status_code == 200, response.text
    record = read_json(rep, customer_id)
    for name in cleared:
        assert record[name] is None, (name, record)
    kept = {k: v for k, v in expected_record(customer_id).items() if k not in cleared}
    assert {k: v for k, v in record.items() if k not in cleared} == kept


@pytest.mark.parametrize("form", ["omitted", "empty-list"])
def test_k01_omitted_or_empty_contacts_read_back_as_no_contacts(crm: Crm, form: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)
    body = edited_body()
    if form == "omitted":
        body.pop("contacts")
    else:
        body["contacts"] = []
    assert edit(rep, customer_id, body).status_code == 200
    assert read_json(rep, customer_id)["contacts"] == []
    assert crm.pg.rows(
        "SELECT count(*) FROM customer_contact WHERE customer_id = %s", (customer_id,)
    ) == [(0,)]


def test_k01_an_omitted_country_reads_back_pl(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, "Gospodarstwo Zagraniczne", country="DE", tax_id="DE-305")
    assert read_json(rep, customer_id)["country"] == "DE"
    response = edit(rep, customer_id, {"name": "Gospodarstwo Krajowe"})
    assert response.status_code == 200, response.text
    record = read_json(rep, customer_id)
    assert (record["country"], record["tax_id"]) == ("PL", None)
    assert crm.pg.rows(
        "SELECT nip, foreign_tax_id FROM customer WHERE id = %s", (customer_id,)
    ) == [(None, None)]


def test_k01_contacts_read_back_in_the_order_sent(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)
    values = ["+48601305101", "c@farm.example.invalid", "+48601305103", "a@farm.example.invalid"]
    contacts = [phone(v) if v.startswith("+") else email(v) for v in values]
    assert edit(rep, customer_id, {"name": "Kolejnosc", "contacts": contacts}).status_code == 200
    assert [c["value"] for c in read_json(rep, customer_id)["contacts"]] == values
    reversed_contacts = list(reversed(contacts))
    assert (
        edit(rep, customer_id, {"name": "Kolejnosc", "contacts": reversed_contacts}).status_code
        == 200
    )
    assert [c["value"] for c in read_json(rep, customer_id)["contacts"]] == values[::-1]


def stored_state(crm: Crm, customer_id: str) -> tuple[Any, ...]:
    """The customer's row and its contacts but for the contacts' own identifiers, which every
    edit issues anew (G-5 A: the list is replaced)."""
    rows, contacts = snapshot(crm)
    return rows[customer_id], [row[1:] for row in contacts.get(customer_id, [])]


def test_k01_a_retried_identical_put_leaves_the_same_stored_state(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **STORED)
    first = edit(rep, customer_id, edited_body())
    after_first = stored_state(crm, customer_id)
    second = edit(rep, customer_id, edited_body())
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.content == second.content
    assert stored_state(crm, customer_id) == after_first
