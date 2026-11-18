"""EKO-3-01 K-03 (CUS-8; G-3 A, P2 `domain.js` l. 56-62): the server stores phones in E.164 with
`+48` by default, and rejects a malformed e-mail or phone along with the whole request, so no
customer and none of its contacts exists afterwards. Sent to the API directly, never the SPA.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create, created_id, listed_ids

pytestmark = pytest.mark.runtime


def phone(value: str) -> dict[str, Any]:
    return {"kind": "phone", "value": value, "primary": False}


def email(value: str) -> dict[str, Any]:
    return {"kind": "email", "value": value, "primary": False}


def stored_values(crm: Crm, customer_id: str) -> list[str]:
    return [
        value
        for (value,) in crm.pg.rows(
            "SELECT value FROM customer_contact WHERE customer_id = %s ORDER BY position",
            (customer_id,),
        )
    ]


def stored_value(crm: Crm, browser: Any, value: str, kind: str = "phone") -> str:
    customer_id = created_id(
        browser, {"name": "Gospodarstwo Telefon", "contacts": [{"kind": kind, "value": value}]}
    )
    [stored] = stored_values(crm, customer_id)
    return stored


def test_k03_a_national_number_gets_plus_48(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    assert stored_value(crm, rep, "601 234 567") == "+48601234567"


def test_k03_contrast_b_a_number_with_its_own_prefix_keeps_it(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    assert stored_value(crm, rep, "+49 30 1234567") == "+49301234567"


def test_k03_a_malformed_last_email_rejects_the_customer_and_every_contact(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    created_id(rep, {"name": "Gospodarstwo Istniejace"})
    before_list, before_counts = listed_ids(rep), crm.counts()
    contacts = [phone("601 234 567"), phone("+49 30 1234567"), email("farm1.example.invalid")]
    response = create(rep, {"name": "Gospodarstwo Odrzucone", "contacts": contacts})
    assert response.status_code == 422, response.text
    assert listed_ids(rep) == before_list
    assert crm.counts() == before_counts


def test_k03_contrast_a_the_same_request_with_a_valid_email_stores_all_three(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    contacts = [phone("601 234 567"), phone("+49 30 1234567"), email("farm1@example.invalid")]
    customer_id = created_id(rep, {"name": "Gospodarstwo Przyjete", "contacts": contacts})
    assert stored_values(crm, customer_id) == [
        "+48601234567",
        "+49301234567",
        "farm1@example.invalid",
    ]
    assert customer_id in listed_ids(rep)


def test_k03_a_phone_with_letters_rejects_the_whole_request(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    before_list, before_counts = listed_ids(rep), crm.counts()
    contacts = [email("farm2@example.invalid"), phone("601 234 ABC")]
    assert create(rep, {"name": "Gospodarstwo Litery", "contacts": contacts}).status_code == 422
    assert listed_ids(rep) == before_list
    assert crm.counts() == before_counts


ACCEPTED_PHONES = {
    "shortest-international": ("+12345678", "+12345678"),
    "longest-international": ("+123456789012345", "+123456789012345"),
    "nine-national-digits": ("601234567", "+48601234567"),
    "brackets-and-hyphens": ("(+48) 60-1234-567", "+48601234567"),
}
REJECTED_PHONES = {
    "one-short-of-shortest": "+1234567",
    "one-past-longest": "+1234567890123456",
    "eight-national-digits": "60123456",
    "ten-national-digits": "60123 45678",
    "first-digit-zero": "+0 123456789",
    "double-zero-prefix": "0048601234567",
    "plus-only": "+",
    "non-ascii-digits": "\u0666\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667",
    "fullwidth-digits": "\uff16\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17",
}


@pytest.mark.parametrize("variant", sorted(ACCEPTED_PHONES))
def test_k03_phone_digit_count_limits_accepted(crm: Crm, variant: str) -> None:
    sent, stored = ACCEPTED_PHONES[variant]
    rep = crm.login(REP_A, ["rep"])
    assert stored_value(crm, rep, sent) == stored


@pytest.mark.parametrize("variant", sorted(REJECTED_PHONES))
def test_k03_phone_digit_count_limits_rejected(crm: Crm, variant: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    body = {"name": "Gospodarstwo Granice", "contacts": [phone(REJECTED_PHONES[variant])]}
    assert create(rep, body).status_code == 422
    assert crm.counts() == before


def test_k03_an_email_is_trimmed_and_keeps_its_case(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    assert stored_value(crm, rep, "  Biuro@Farm3.Example.Invalid  ", "email") == (
        "Biuro@Farm3.Example.Invalid"
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("biuro @farm4.example.invalid", id="space-inside"),
        pytest.param("biuro@farm4.example\tinvalid", id="tab-inside"),
        pytest.param("biuro@farm4", id="no-dot-in-domain"),
        pytest.param("@farm4.example.invalid", id="no-local-part"),
        pytest.param("biuro@@farm4.example.invalid", id="two-at-signs"),
    ],
)
def test_k03_a_malformed_email_is_rejected(crm: Crm, value: str) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    assert create(rep, {"name": "Gospodarstwo Mail", "contacts": [email(value)]}).status_code == 422
    assert crm.counts() == before


EMAIL_LIMIT = 254


def test_k03_hs10b_an_email_at_254_characters_is_accepted_and_one_past_is_rejected(
    crm: Crm,
) -> None:
    """HS10 (b) A (Issue #195, 2026-11-18): an e-mail contact value is at most 254 characters,
    counted after trimming, on the NFC form."""
    domain = "@farm5.example.invalid"
    at_limit = "a" * (EMAIL_LIMIT - len(domain)) + domain
    assert len(at_limit) == EMAIL_LIMIT
    rep = crm.login(REP_A, ["rep"])
    assert stored_value(crm, rep, f"  {at_limit}  ", "email") == at_limit
    before = crm.counts()
    past = "a" + at_limit
    assert create(rep, {"name": "Gospodarstwo Mail", "contacts": [email(past)]}).status_code == 422
    assert crm.counts() == before
