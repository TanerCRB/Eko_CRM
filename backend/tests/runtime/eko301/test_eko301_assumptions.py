"""EKO-3-01 assumptions for gate 2 (A-02 to A-08 of the backend report): gaps the criteria leave
open, closed by the backend developer and pinned here so the human can accept or reject each.
Written after the code they pin; each one is listed in the report's assumption ledger.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm, create, created_id, customer_url

pytestmark = pytest.mark.runtime

NBSP = chr(0xA0)


def test_a02_primary_may_be_omitted_and_means_not_primary(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(
        rep, {"name": "Gospodarstwo A02", "contacts": [{"kind": "phone", "value": "601234567"}]}
    )
    [contact] = rep.send("GET", customer_url(customer_id)).json()["contacts"]
    assert contact == {"kind": "phone", "value": "+48601234567", "note": None, "primary": False}


def test_a03_a_note_is_not_trimmed_and_a_whitespace_only_note_is_kept(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    notes = ["  Pan Jan  ", "   "]
    contacts = [
        {"kind": "phone", "value": f"60123456{n}", "note": note} for n, note in enumerate(notes)
    ]
    customer_id = created_id(rep, {"name": "Gospodarstwo A03", "contacts": contacts})
    read = rep.send("GET", customer_url(customer_id)).json()["contacts"]
    assert [c["note"] for c in read] == notes


def test_a05_contacts_null_is_rejected(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    assert create(rep, {"name": "Gospodarstwo A05", "contacts": None}).status_code == 422
    assert crm.counts() == before


def test_a06_a_list_item_is_the_identifier_name_and_country_only(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(
        rep,
        {
            "name": "Gospodarstwo A06",
            "contacts": [{"kind": "email", "value": "a06@farm.example.invalid"}],
        },
    )
    listed = rep.send("GET", CUSTOMERS).json()
    assert listed == {
        "items": [
            {"id": customer_id, "name": "Gospodarstwo A06", "country": "PL", "archived": False}
        ]
    }


STRICT: dict[str, dict[str, Any]] = {
    "primary-as-string": {"contacts": [{"kind": "phone", "value": "601234567", "primary": "true"}]},
    "primary-as-number": {"contacts": [{"kind": "phone", "value": "601234567", "primary": 1}]},
    "phone-as-number": {"contacts": [{"kind": "phone", "value": 601234567}]},
    "unknown-contact-field": {"contacts": [{"kind": "phone", "value": "601234567", "id": "x"}]},
    "unknown-kind": {"contacts": [{"kind": "fax", "value": "601234567"}]},
}


@pytest.mark.parametrize("variant", sorted(STRICT))
def test_a07_json_types_are_strict_and_unknown_fields_are_rejected(crm: Crm, variant: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    assert create(rep, {"name": "Gospodarstwo A07", **STRICT[variant]}).status_code == 422
    assert crm.counts() == before


@pytest.mark.parametrize(
    ("sent", "accepted"),
    [
        pytest.param("601.234.567", False, id="dots-are-not-separators"),
        pytest.param("60" + NBSP + "1234" + NBSP + "567", True, id="no-break-spaces-are"),
    ],
)
def test_a08_phone_separators_are_whitespace_brackets_and_hyphens(
    crm: Crm, sent: str, accepted: bool
) -> None:
    rep = crm.login(REP_A, ["rep"])
    response = create(
        rep, {"name": "Gospodarstwo A08", "contacts": [{"kind": "phone", "value": sent}]}
    )
    assert response.status_code == (201 if accepted else 422), response.text
