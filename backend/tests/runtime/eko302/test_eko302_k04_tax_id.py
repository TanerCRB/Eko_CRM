"""EKO-3-02 K-04 (CUS-5; G-1 A, G-2 A, G-4 A, G-7 A; ADR-0002 addendum draft of EKO-3-02,
accepted at gate 1): a Polish tax ID has surrounding whitespace, hyphens, spaces and a leading
`PL` removed, must then be ten ASCII digits with a valid checksum, and is stored and returned as
the ten digits; a foreign tax ID is free text with no checksum, stored in its own column.

Until EKO-3-03 no uniqueness applies: a NIP another rep's customer holds gets exactly the answer
a NIP nobody holds gets (PRH-4). Every NIP is synthetic and built at run time (G-7 A).
"""

import string
from typing import Any

import pytest

from tests.runtime.eko301.conftest import (
    REP_A,
    REP_B,
    Crm,
    create,
    created_id,
    customer_url,
)
from tests.runtime.eko302.conftest import NAME, errors_at, stored
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime


def refused_at(crm: Crm, tax_id: Any, country: str = "PL") -> list[tuple[Any, ...]]:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    locations = errors_at(create(rep, {"name": NAME, "country": country, "tax_id": tax_id}))
    assert crm.counts() == before
    return locations


def tax_id_of(crm: Crm, tax_id: Any, country: str = "PL") -> tuple[Any, dict[str, Any]]:
    rep = crm.login(REP_A, ["rep"])
    customer_id = created_id(rep, {"name": NAME, "country": country, "tax_id": tax_id})
    read = rep.send("GET", customer_url(customer_id)).json()
    return read["tax_id"], stored(crm, customer_id)


def test_k04_one_nip_four_spellings_read_back_identical(crm: Crm) -> None:
    nip = nips.valid_nip(3003)
    spellings = [nip, nips.hyphenated(nip), nips.spaced(nip), "PL" + nip]
    assert len(set(spellings)) == 4
    for spelling in spellings:
        read, row = tax_id_of(crm, spelling)
        assert read == nip, spelling
        assert (row["nip"], row["foreign_tax_id"]) == (nip, None)
    assert crm.counts()["customer"] == 4


def test_k04_wrong_checksum_rejected(crm: Crm) -> None:
    nip = nips.valid_nip(3003)
    assert refused_at(crm, nips.wrong_check_digit(nip)) == [("tax_id",)]
    assert refused_at(crm, nips.hyphenated(nips.wrong_check_digit(nip))) == [("tax_id",)]


def test_k04_contrast_the_rejected_text_is_stored_as_given_for_a_foreign_customer(
    crm: Crm,
) -> None:
    wrong = nips.hyphenated(nips.wrong_check_digit(nips.valid_nip(3003)))
    read, row = tax_id_of(crm, wrong, "DE")
    assert read == wrong
    assert (row["nip"], row["foreign_tax_id"]) == (None, wrong)


def test_k04_remainder_ten_rejected(crm: Crm) -> None:
    ten = nips.remainder_ten_digits(0)
    for digit in string.digits:
        assert refused_at(crm, ten[:9] + digit) == [("tax_id",)]


def rejected_spellings() -> dict[str, str]:
    nip = nips.valid_nip(4004)
    return {
        "nine-digits": nip[:9],
        "eleven-digits": nip + "1",
        "letters": nip[:5] + "ABCDE",
        "dots": ".".join((nip[0:3], nip[3:6], nip[6:8], nip[8:10])),
        "slashes": "/".join((nip[0:3], nip[3:6], nip[6:8], nip[8:10])),
        "pl-in-the-middle": nip[:5] + "PL" + nip[5:],
        "pl-at-the-end": nip + "PL",
        "full-width-digits": nips.other_digits(nip, 0xFF10),
        "arabic-indic-digits": nips.other_digits(nip, 0x0660),
        "33-characters-as-sent": nip[:5] + " " * 23 + nip[5:],
        "pl-alone": "PL",
        "two-hyphens": "--",
        "tab-inside": nip[:5] + "\t" + nip[5:],
        "pl-twice": "PLPL" + nip,
    }


@pytest.mark.parametrize("variant", sorted(rejected_spellings()))
def test_k04_not_a_nip_is_rejected(crm: Crm, variant: str) -> None:
    spelling = rejected_spellings()[variant]
    if variant == "33-characters-as-sent":
        assert len(spelling) == 33
        assert spelling.replace(" ", "") == nips.valid_nip(4004)
    assert refused_at(crm, spelling) == [("tax_id",)]


def test_k04_at_32_characters_as_sent_a_nip_is_accepted(crm: Crm) -> None:
    nip = nips.valid_nip(4004)
    spelling = nip[:5] + " " * 22 + nip[5:]
    assert len(spelling) == 32
    assert tax_id_of(crm, spelling)[0] == nip


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param("  {}  ", id="surrounding-spaces"),
        pytest.param("PL {}", id="space-after-pl"),
        pytest.param(" PL-{} ", id="pl-hyphen-and-spaces"),
        pytest.param("pl{}", id="lower-case-pl"),
    ],
)
def test_k04_accepted_spellings(crm: Crm, spelling: str) -> None:
    nip = nips.valid_nip(5005)
    assert tax_id_of(crm, spelling.format(nips.hyphenated(nip)))[0] == nip


@pytest.mark.parametrize("not_given", [None, "", "   "])
def test_k04_null_empty_or_blank_is_no_tax_id(crm: Crm, not_given: Any) -> None:
    read, row = tax_id_of(crm, not_given)
    assert read is None
    assert (row["nip"], row["foreign_tax_id"]) == (None, None)


@pytest.mark.parametrize(
    "foreign",
    ["DE123456789", "ATU12345678", "FR 12 345678901", "123", "  GB 123 4567 89  ", "PL"],
)
def test_k04_foreign_tax_id_free_text(crm: Crm, foreign: str) -> None:
    read, row = tax_id_of(crm, foreign, "DE")
    assert read == foreign.strip()
    assert (row["nip"], row["foreign_tax_id"]) == (None, foreign.strip())


def test_k04_a_nip_another_reps_customer_holds_gets_the_answer_an_unused_nip_gets(
    crm: Crm,
) -> None:
    held, unused = nips.valid_nip(6006), nips.valid_nip(7007)
    owner = crm.login(REP_A, ["rep"])
    created_id(owner, {"name": "Gospodarstwo Rep A", "street": "ul. Ukryta 7", "tax_id": held})
    rep_b = crm.login(REP_B, ["rep"])
    on_held = create(rep_b, {"name": NAME, "tax_id": held})
    on_unused = create(rep_b, {"name": NAME, "tax_id": unused})
    assert on_held.status_code == on_unused.status_code == 201, on_held.text
    first, second = on_held.json(), on_unused.json()
    assert first["tax_id"] == held and second["tax_id"] == unused
    strip = ("id", "tax_id")
    assert {k: v for k, v in first.items() if k not in strip} == {
        k: v for k, v in second.items() if k not in strip
    }
    assert "Rep A" not in on_held.text and "Ukryta" not in on_held.text
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE nip = %s", (held,)) == [(2,)]
