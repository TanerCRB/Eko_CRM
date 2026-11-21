"""EKO-3-02 K-05 (CUS-3; ADR-0005: no personal data in a message or a log line): a request refused
by any rule of this task stores nothing, names the rejected field in `loc`, and repeats none of
the submitted values in its answer or in any log record the backend writes.

Each case is one body carrying a distinctive synthetic value, sent straight to the API; the body
also carries a contact, so "stores nothing" covers the contacts too. Every NIP is built at run
time (G-7 A).
"""

import logging
from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create
from tests.runtime.eko302.conftest import NAME, errors_at
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

CONTACT = {"kind": "email", "value": "k05@farm.example.invalid", "primary": True}


def cases() -> dict[str, tuple[dict[str, Any], str, str, dict[str, Any]]]:
    """name -> (refused fields, value that must not come back, field, corrected fields)."""
    nip = nips.valid_nip(8008)
    wrong = nips.wrong_check_digit(nips.valid_nip(8118))
    return {
        "street-over-bound": (
            {"street": "UlicaZnacznikK05" + "s" * 140},
            "UlicaZnacznikK05",
            "street",
            {"street": "UlicaZnacznikK05"},
        ),
        "street-over-raw-cap": (
            {"street": "UlicaSurowaK05" + " " * 600},
            "UlicaSurowaK05",
            "street",
            {"street": "UlicaSurowaK05"},
        ),
        "street-with-nul": (
            {"street": "UlicaZeroK05\x00"},
            "UlicaZeroK05",
            "street",
            {"street": "UlicaZeroK05"},
        ),
        "town-over-bound": (
            {"town": "MiastoZnacznikK05" + "t" * 90},
            "MiastoZnacznikK05",
            "town",
            {"town": "MiastoZnacznikK05"},
        ),
        "polish-postal-code": (
            {"postal_code": "77-77K"},
            "77-77K",
            "postal_code",
            {"postal_code": "77-777"},
        ),
        "foreign-postal-code-over-bound": (
            {"country": "DE", "postal_code": "KodZnacznikK05-xxxxxx"},
            "KodZnacznikK05",
            "postal_code",
            {"country": "DE", "postal_code": "KodZnacznikK05"},
        ),
        "unknown-voivodeship": (
            {"voivodeship": "znacznikowskie"},
            "znacznikowskie",
            "voivodeship",
            {"voivodeship": "lubuskie"},
        ),
        "county-of-another-voivodeship": (
            {"voivodeship": "mazowieckie", "county": "kołobrzeski"},
            "kołobrzeski",
            "county",
            {"voivodeship": "zachodniopomorskie", "county": "kołobrzeski"},
        ),
        "county-without-voivodeship": (
            {"county": "gołdapski"},
            "gołdapski",
            "county",
            {"voivodeship": "warmińsko-mazurskie", "county": "gołdapski"},
        ),
        "foreign-voivodeship": (
            {"country": "DE", "voivodeship": "pomorskie"},
            "pomorskie",
            "voivodeship",
            {"country": "DE"},
        ),
        "foreign-county": (
            {"country": "DE", "county": "lęborski"},
            "lęborski",
            "county",
            {"country": "DE"},
        ),
        "nip-checksum": (
            {"tax_id": nips.hyphenated(wrong)},
            wrong,
            "tax_id",
            {"tax_id": nips.hyphenated(nip)},
        ),
        "nip-shape": (
            {"tax_id": "PL" + nip + "X"},
            nip,
            "tax_id",
            {"tax_id": "PL" + nip},
        ),
        "foreign-tax-id-over-bound": (
            {"country": "DE", "tax_id": "PodatekZnacznikK05-" + "x" * 20},
            "PodatekZnacznikK05",
            "tax_id",
            {"country": "DE", "tax_id": "PodatekZnacznikK05"},
        ),
    }


def logged_text(records: list[logging.LogRecord]) -> str:
    formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(formatter.format(r) + " " + repr(vars(r)) for r in records)


def hyphen_forms(value: str) -> list[str]:
    if len(value) == 10 and value.isdigit():
        return [value, nips.hyphenated(value), nips.spaced(value)]
    return [value]


@pytest.mark.parametrize("case", sorted(cases()))
def test_k05_a_refused_rule_stores_nothing_names_its_field_and_repeats_no_value(
    crm: Crm, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    refused, value, field, corrected = cases()[case]
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    response = create(rep, {"name": NAME, "contacts": [CONTACT], **refused})
    assert errors_at(response) == [(field,)]
    assert crm.counts() == before
    logged = logged_text(caplog.records)
    assert caplog.records, "no log record at all: the capture would pass vacuously"
    for form in hyphen_forms(value):
        assert form not in response.text, form
        assert form not in logged, form

    # Contrast: only the offending value corrected, and one customer with its contact is stored.
    fixed = create(rep, {"name": NAME, "contacts": [CONTACT], **corrected})
    assert fixed.status_code == 201, fixed.text
    assert crm.counts() == {
        "customer_contact": before["customer_contact"] + 1,
        "customer": before["customer"] + 1,
    }


def test_k05_several_invalid_fields_give_one_located_error_each_with_no_value(
    crm: Crm,
) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    wrong = nips.wrong_check_digit(nips.valid_nip(9009))
    body = {
        "name": NAME,
        "street": "UlicaWieleK05" + "s" * 150,
        "town": "MiastoWieleK05" + "t" * 100,
        "postal_code": "1-2345",
        "voivodeship": "wieloznacznikowskie",
        "county": "nieoceniany",
        "tax_id": wrong,
        "contacts": [CONTACT, {**CONTACT, "primary": False}],
    }
    response = create(rep, body)
    assert sorted(errors_at(response)) == sorted(
        [("street",), ("postal_code",), ("town",), ("voivodeship",), ("tax_id",)]
    )
    assert crm.counts() == before
    for value in ("UlicaWieleK05", "MiastoWieleK05", "1-2345", "wieloznacznikowskie", wrong):
        assert value not in response.text
    assert "nieoceniany" not in response.text
    for error in response.json()["detail"]:
        assert len(error["msg"]) <= 200
