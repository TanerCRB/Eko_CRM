"""EKO-3-01 fix round 1, Reviewer R-01 / Security Auditor B-01 (decision A on Issue #195): a
request body is bounded before it is decoded, after the access decision.

- A body of exactly `REQUEST_BODY_LIMIT` bytes reaches validation; one byte more is 413
  `{"detail": "request body too large"}` with `no-store`, and nothing is stored.
- A body sent without `Content-Length` is counted as it arrives and cut off the same way.
- An anonymous or foreign-Origin oversized body still gets the access answer (ADR-0003-C34).
- Raw text fields are capped before NFC runs, at four times the NFC bound (the most code points
  NFC composes into one character), so a decomposed value valid after NFC is still accepted and
  a 422 for an over-long value or list does not echo it.
"""

import json
import unicodedata
from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.eko201.conftest import ORIGIN
from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm

pytestmark = pytest.mark.runtime

LIMIT = 2 * 1024 * 1024
TOO_LARGE = (413, {"detail": "request body too large"})
# U+1F82 decomposes into four code points, the most any character composes from.
FOUR_TO_ONE = unicodedata.normalize("NFD", "ᾂ")


def padded(body: dict[str, Any], size: int) -> bytes:
    """`body` as JSON followed by insignificant whitespace, `size` bytes in all."""
    encoded = json.dumps(body).encode("ascii")
    assert len(encoded) <= size
    return encoded + b" " * (size - len(encoded))


def post(crm: Crm, browser: Any, content: Any, **headers: str) -> Any:
    return browser.send(
        "POST",
        CUSTOMERS,
        content=content,
        headers={"content-type": "application/json", **headers},
    )


def test_r01_a_body_at_the_limit_reaches_validation_and_one_byte_more_is_413(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    at_limit = post(crm, rep, padded({"name": "Gospodarstwo Granica"}, LIMIT))
    assert at_limit.status_code == 201, at_limit.text
    before = crm.counts()
    past = post(crm, rep, padded({"name": "Gospodarstwo Za Duze"}, LIMIT + 1))
    assert (past.status_code, past.json()) == TOO_LARGE
    assert past.headers.get_list("cache-control") == ["no-store"]
    assert crm.counts() == before


def chunks(total: int, size: int = 64 * 1024) -> Iterator[bytes]:
    yield b'{"name": "Gospodarstwo Strumien"'
    sent = 32
    while sent < total:
        piece = b" " * min(size, total - sent)
        sent += len(piece)
        yield piece
    yield b"}"


def test_r01_a_body_without_a_length_is_counted_and_cut_off(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = post(crm, rep, chunks(LIMIT + 1024))
    assert "content-length" not in {k.lower() for k in response.request.headers}
    assert (response.status_code, response.json()) == TOO_LARGE
    assert crm.counts() == before


@pytest.mark.parametrize(
    ("label", "origin", "expected"),
    [
        pytest.param("no-session", ORIGIN, (401, {"detail": "not authenticated"}), id="anonymous"),
        pytest.param(
            "session", "https://elsewhere.test", (403, {"detail": "origin refused"}), id="foreign"
        ),
    ],
)
def test_r01_an_oversized_body_still_gets_the_access_answer_first(
    crm: Crm, label: str, origin: str, expected: tuple[int, Any]
) -> None:
    browser = crm.open_browser(crm.app) if label == "no-session" else crm.login(REP_A, ["rep"])
    response = browser.send(
        "POST",
        CUSTOMERS,
        origin=origin,
        content=padded({"name": "Gospodarstwo"}, LIMIT + 1),
        headers={"content-type": "application/json"},
    )
    assert (response.status_code, response.json()) == expected


def test_r01_decomposed_values_valid_after_nfc_pass_the_raw_caps(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    name = FOUR_TO_ONE * 120
    local = FOUR_TO_ONE * (254 - len("@b.cd"))
    address = local + "@b.cd"
    note = FOUR_TO_ONE * 500
    assert (len(name), len(address), len(note)) == (480, 4 * 249 + 5, 2000)
    assert len(unicodedata.normalize("NFC", address)) == 254
    body = {"name": name, "contacts": [{"kind": "email", "value": address, "note": note}]}
    response = rep.send("POST", CUSTOMERS, json=body)
    assert response.status_code == 201, response.text[:300]


@pytest.mark.parametrize(
    ("body", "cap"),
    [
        pytest.param({"name": "N" * 100_000}, 480, id="name"),
        pytest.param(
            {"name": "G", "contacts": [{"kind": "email", "value": "v" * 100_000}]}, 1016, id="value"
        ),
        pytest.param(
            {
                "name": "G",
                "contacts": [{"kind": "phone", "value": "+48601000001", "note": "n" * 100_000}],
            },
            2000,
            id="note",
        ),
        pytest.param(
            {"name": "G", "contacts": [{"kind": "phone", "value": "x" * 900}] * 2000},
            1016,
            id="list",
        ),
    ],
)
def test_r01_a_422_for_an_over_long_value_echoes_nothing_past_the_raw_cap(
    crm: Crm, body: dict[str, Any], cap: int
) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = rep.send("POST", CUSTOMERS, json=body)
    assert response.status_code == 422, response.text[:300]
    assert crm.counts() == before
    for error in response.json()["detail"]:
        echoed = json.dumps(error.get("input", ""))
        assert len(echoed) <= cap + 2, (error["type"], error["loc"], len(echoed))
