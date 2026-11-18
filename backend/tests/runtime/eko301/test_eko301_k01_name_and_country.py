"""EKO-3-01 K-01 (CUS-2; ADR-0002 l. 100-101, G-1 A, G-2 A, G-3 A): a customer sent with only a
name is saved and its country reads back as Poland; the name is stored as the NFC of the trimmed
input, checked on the stored row as well as through the API's read; every "missing name" edge is
rejected and stores nothing.

Sent straight to the API by a rep's real session, never through the SPA.
"""

import unicodedata
from typing import Any

import pytest

from tests.runtime.eko301.conftest import (
    REP_A,
    Crm,
    create,
    created_id,
    customer_url,
    listed_ids,
)

pytestmark = pytest.mark.runtime

NAME_LIMIT = 120
DECOMPOSED = "Gospodarstwo Zo\u0301\u0142"
COMPOSED = "Gospodarstwo \u017b\u00f3\u0142\u0107"


def stored_row(crm: Crm, customer_id: str) -> tuple[str, str]:
    """The row as PostgreSQL holds it, read outside the API."""
    [(name, country)] = crm.pg.rows(
        "SELECT name, country FROM customer WHERE id = %s", (customer_id,)
    )
    return name, country


def code_points(text: str) -> list[int]:
    return [ord(c) for c in text]


def test_k01_a_name_only_customer_reads_back_with_country_poland(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": "  Gospodarstwo Testowe 01  "})
    read = rep.send("GET", customer_url(customer_id))
    assert read.status_code == 200, read.text
    assert (read.json()["name"], read.json()["country"]) == ("Gospodarstwo Testowe 01", "PL")
    assert stored_row(crm, customer_id) == ("Gospodarstwo Testowe 01", "PL")


def test_k01_contrast_a_country_sent_is_kept(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": "Gospodarstwo Testowe 02", "country": "DE"})
    assert rep.send("GET", customer_url(customer_id)).json()["country"] == "DE"
    assert stored_row(crm, customer_id) == ("Gospodarstwo Testowe 02", "DE")


MISSING_NAME: dict[str, dict[str, Any]] = {
    "omitted": {},
    "null": {"name": None},
    "empty": {"name": ""},
    "spaces": {"name": "   "},
    "whitespace-mix": {"name": " \t\n" + chr(0xA0)},
}


@pytest.mark.parametrize("variant", sorted(MISSING_NAME))
def test_k01_contrast_b_a_missing_name_is_rejected_and_nothing_is_stored(
    crm: Crm, variant: str
) -> None:
    rep = crm.login(REP_A, ["rep"])
    created_id(rep, {"name": "Gospodarstwo Testowe 03"})
    before_list, before_counts = listed_ids(rep), crm.counts()
    response = create(rep, {**MISSING_NAME[variant], "country": "PL"})
    assert response.status_code == 422, response.text
    assert listed_ids(rep) == before_list
    assert crm.counts() == before_counts


def test_k01_a_decomposed_name_is_stored_composed(crm: Crm) -> None:
    expected = unicodedata.normalize("NFC", DECOMPOSED)
    assert code_points(DECOMPOSED) != code_points(expected), "the edge would pass vacuously"
    assert "\u00f3" in expected
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": DECOMPOSED})
    assert code_points(rep.send("GET", customer_url(customer_id)).json()["name"]) == code_points(
        expected
    )
    assert code_points(stored_row(crm, customer_id)[0]) == code_points(expected)


def test_k01_a_composed_polish_name_reads_back_identical(crm: Crm) -> None:
    assert unicodedata.normalize("NFC", COMPOSED) == COMPOSED
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": COMPOSED})
    assert code_points(rep.send("GET", customer_url(customer_id)).json()["name"]) == code_points(
        COMPOSED
    )
    assert code_points(stored_row(crm, customer_id)[0]) == code_points(COMPOSED)


def test_k01_the_name_length_limit_is_counted_on_the_nfc_form(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    at_limit = "G" * NAME_LIMIT
    assert create(rep, {"name": at_limit}).status_code == 201
    before = crm.counts()
    past = create(rep, {"name": "G" * (NAME_LIMIT + 1)})
    assert past.status_code == 422, past.text
    assert crm.counts() == before
    # 121 code points as sent, 120 once composed: accepted, and stored composed.
    decomposed = "G" * (NAME_LIMIT - 1) + "o\u0301"
    assert len(decomposed) == NAME_LIMIT + 1
    assert len(unicodedata.normalize("NFC", decomposed)) == NAME_LIMIT
    customer_id = created_id(rep, {"name": decomposed})
    assert stored_row(crm, customer_id)[0] == "G" * (NAME_LIMIT - 1) + "\u00f3"
    # Spaces at the edges are trimmed before counting.
    assert create(rep, {"name": f"  {at_limit}  "}).status_code == 201


COUNTRY_REJECTED: dict[str, Any] = {
    "null": None,
    "empty": "",
    "unknown-code": "XX",
    "lower-case": "de",
    "a-name": "Germany",
    "padded": " DE",
}


@pytest.mark.parametrize("variant", sorted(COUNTRY_REJECTED))
def test_k01_country_null_empty_or_outside_the_list_is_rejected(crm: Crm, variant: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = create(
        rep, {"name": "Gospodarstwo Testowe 04", "country": COUNTRY_REJECTED[variant]}
    )
    assert response.status_code == 422, response.text
    assert crm.counts() == before


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b'{"name": "Gospodarstwo \ud800"}', id="name"),
        pytest.param(
            b'{"name": "Gospodarstwo", "contacts": [{"kind": "phone", "value": "+48601000001",'
            b' "note": "Pani \udc00"}]}',
            id="note",
        ),
        pytest.param(b'{"name": "Gospodarstwo \u0000"}', id="nul-in-name"),
    ],
)
def test_k01_assumption_text_that_cannot_be_stored_is_rejected(crm: Crm, body: bytes) -> None:
    """A-04: a lone surrogate or U+0000 decodes from JSON but cannot be stored as UTF-8 text."""
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = rep.send(
        "POST", "/api/customers", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422, response.text
    assert crm.counts() == before
