"""EKO-3-01 fix round 1, QA contrasts for the raw caps of R-01 / B-01 (decision A on Issue #195).

The raw caps sit exactly at four times the NFC bound and run before trimming, so padding past the
cap is refused even where the trimmed value would be valid (assumption A-12), and the value at the
cap itself is still accepted. Each pair below differs in one code point. A 422 for a value past a
cap names `string_too_long` and does not echo it. Since fix round 2 (decision D on Issue #195) a
422 for a short value does not echo it either: no error carries `input`, while `loc` and `type`
still name what was refused. Every value is synthetic (ADR-0005).
"""

import unicodedata
from typing import Any

import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm

pytestmark = pytest.mark.runtime

FOUR_TO_ONE = unicodedata.normalize("NFD", "ᾂ")
NAME = "Gospodarstwo Odstep"
PHONE = "+48601000301"


def only_error(response: Any) -> dict[str, Any]:
    assert response.status_code == 422, response.text[:300]
    errors: list[dict[str, Any]] = response.json()["detail"]
    assert len(errors) == 1, errors
    return errors[0]


def test_qa_r01_a_name_padded_to_the_raw_cap_is_stored_trimmed(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    response = rep.send("POST", CUSTOMERS, json={"name": NAME.ljust(480)})
    assert response.status_code == 201, response.text[:300]
    assert response.json()["name"] == NAME


def test_qa_r01_a_name_padded_one_space_past_the_raw_cap_is_refused_unechoed(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    error = only_error(rep.send("POST", CUSTOMERS, json={"name": NAME.ljust(481)}))
    assert (error["type"], error["loc"]) == ("string_too_long", ["body", "name"])
    assert "input" not in error
    assert crm.counts() == before


def test_qa_r01_a_phone_padded_with_separators_to_the_raw_cap_is_stored(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    contact = {"kind": "phone", "value": PHONE.ljust(1015) + "1"}
    assert len(contact["value"]) == 1016
    response = rep.send("POST", CUSTOMERS, json={"name": NAME, "contacts": [contact]})
    assert response.status_code == 201, response.text[:300]
    assert response.json()["contacts"][0]["value"] == "+486010003011"


def test_qa_r01_a_phone_padded_one_separator_past_the_raw_cap_is_refused(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    contact = {"kind": "phone", "value": PHONE.ljust(1016) + "1"}
    body = {"name": NAME, "contacts": [contact]}
    error = only_error(rep.send("POST", CUSTOMERS, json=body))
    assert (error["type"], error["loc"]) == ("string_too_long", ["body", "contacts", 0, "value"])
    assert "input" not in error
    assert crm.counts() == before


def test_qa_r01_a_note_one_code_point_past_the_raw_cap_is_refused_unechoed(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    contact = {"kind": "phone", "value": PHONE, "note": FOUR_TO_ONE * 500 + "n"}
    error = only_error(rep.send("POST", CUSTOMERS, json={"name": NAME, "contacts": [contact]}))
    assert (error["type"], error["loc"]) == ("string_too_long", ["body", "contacts", 0, "note"])
    assert "input" not in error


def test_qa_r01_an_over_long_country_is_refused_unechoed(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    error = only_error(rep.send("POST", CUSTOMERS, json={"name": NAME, "country": "P" * 100_000}))
    assert (error["type"], error["loc"]) == ("string_too_long", ["body", "country"])
    assert "input" not in error


def test_qa_r01_contrast_a_short_rejected_country_is_named_but_not_echoed(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    error = only_error(rep.send("POST", CUSTOMERS, json={"name": NAME, "country": "XX"}))
    assert (error["type"], error["loc"]) == ("value_error", ["body", "country"])
    assert "input" not in error
