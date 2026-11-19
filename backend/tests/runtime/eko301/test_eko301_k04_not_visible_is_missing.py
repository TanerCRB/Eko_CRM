"""EKO-3-01 K-04 (ACC-4, PRH-4; C-1 A; ADR-0003 addendum of EKO-3-01, section 3; ADR-0003-C33,
by-id half): rep B, who holds `rep`, asking for rep A's customer by its real identifier gets
exactly the answer B gets for a well-formed identifier that exists nowhere: the same status, body
and headers, `Eko-Correlation-Id` aside, with no field value of A's customer in it. The manager,
an account holding `rep` and `manager`, and A itself get the record, so the identifier is real.
"""

import uuid
from typing import Any

import httpx
import pytest

from tests.runtime.eko301.conftest import (
    MANAGER,
    REP_A,
    REP_AND_MANAGER,
    REP_B,
    Crm,
    created_id,
    customer_url,
)

pytestmark = pytest.mark.runtime

CORRELATION = "eko-correlation-id"
SECRET_NAME = "Gospodarstwo Tajne K04"
SECRET_PHONE = "+48601404404"
SECRET_EMAIL = "tajne-k04@farm.example.invalid"
SECRET_NOTE = "Tylko dla przedstawiciela A"
BODY: dict[str, Any] = {
    "name": SECRET_NAME,
    "contacts": [
        {"kind": "phone", "value": SECRET_PHONE, "note": SECRET_NOTE, "primary": True},
        {"kind": "email", "value": SECRET_EMAIL, "note": "Druga notatka K04"},
    ],
}


def answer(response: httpx.Response) -> tuple[int, bytes, list[tuple[str, str]]]:
    headers = sorted((k.lower(), v) for k, v in response.headers.multi_items())
    return response.status_code, response.content, [h for h in headers if h[0] != CORRELATION]


@pytest.fixture
def owned(crm: Crm) -> str:
    return created_id(crm.login(REP_A, ["rep"]), BODY)


def test_k04_another_reps_customer_is_answered_as_an_identifier_that_exists_nowhere(
    crm: Crm, owned: str
) -> None:
    rep_b = crm.login(REP_B, ["rep"])
    nowhere = str(uuid.uuid4())
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE id = %s", (nowhere,)) == [(0,)]
    denied = rep_b.send("GET", customer_url(owned))
    missing = rep_b.send("GET", customer_url(nowhere))
    assert denied.status_code == 404, denied.text
    assert answer(denied) == answer(missing)
    assert denied.headers[CORRELATION] != missing.headers[CORRELATION]
    for value in (SECRET_NAME, SECRET_PHONE, SECRET_EMAIL, SECRET_NOTE, "Druga notatka K04", owned):
        assert value.encode() not in denied.content
        assert all(value not in v for _, v in denied.headers.multi_items())


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(MANAGER, ["manager"], id="manager"),
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
        pytest.param(REP_A, ["rep"], id="the-owner"),
    ],
)
def test_k04_contrast_the_same_identifier_reads_the_full_record(
    crm: Crm, owned: str, subject: str, roles: list[str]
) -> None:
    reader = crm.login(subject, roles)
    read = reader.send("GET", customer_url(owned))
    assert read.status_code == 200, read.text
    record = read.json()
    assert (record["id"], record["name"]) == (owned, SECRET_NAME)
    assert [(c["value"], c["note"]) for c in record["contacts"]] == [
        (SECRET_PHONE, SECRET_NOTE),
        (SECRET_EMAIL, "Druga notatka K04"),
    ]


@pytest.mark.parametrize(
    "malformed",
    [
        pytest.param("not-a-uuid", id="word"),
        pytest.param("12345", id="number"),
    ],
)
def test_k04_a_malformed_identifier_is_refused_on_its_own_terms(
    crm: Crm, owned: str, malformed: str
) -> None:
    rep_b = crm.login(REP_B, ["rep"])
    response = rep_b.send("GET", customer_url(malformed))
    assert response.status_code == 422, response.text
    assert SECRET_NAME.encode() not in response.content
    assert owned.encode() not in response.content
