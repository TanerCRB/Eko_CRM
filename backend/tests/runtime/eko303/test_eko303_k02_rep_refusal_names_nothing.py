"""EKO-3-03 K-02 (CUS-6, PRH-4, ACC-8; G-3 A; ADR-0003-C38 of the gate-1 draft): a rep's refusal
is byte-equal whether the stored customer holding the NIP is the rep's own or another rep's,
carries the fixed CUS-6 text, and names nothing about that customer. The guard is what the
refusal holds, so the absent bytes are asserted, not the by-id read.
"""

import httpx
import pytest

from tests.runtime.eko301.conftest import REP_A, REP_B, Crm, create, created_id
from tests.runtime.eko303.conftest import (
    NIP_TAKEN_BODY,
    REP_C,
    body,
    full_body,
    same_answer,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

MARKERS = ("Znacznikowo-K02", "ul. Znacznikowa K02", "Pan K02", "k02@farm.example.invalid")
X_BODY = {
    "name": "Gospodarstwo Znacznikowo-K02",
    "street": "ul. Znacznikowa K02",
    "town": "Znacznikowo-K02",
    "contacts": [
        {"kind": "email", "value": "k02@farm.example.invalid", "note": "Pan K02", "primary": True}
    ],
}


def spellings(nip: str) -> tuple[str, ...]:
    return (nip, nips.hyphenated(nip), nips.spaced(nip), nip[:3], nip[-4:])


def names_nothing(response: httpx.Response, *needles: str) -> list[str]:
    text = response.text
    found = [needle for needle in needles if needle in text]
    if any(character.isdigit() for character in text):
        found.append("a digit (an identifier, a NIP or a count)")
    return found


def test_k02_own_and_another_reps_customer_get_one_byte_equal_refusal(crm: Crm) -> None:
    n, m, p = nips.valid_nip(32101), nips.valid_nip(32202), nips.valid_nip(32303)
    rep_a = crm.login(REP_A, ["rep"])
    x = created_id(rep_a, {**X_BODY, "tax_id": n})
    created_id(rep_a, body("Gospodarstwo K02 P", p))
    rep_b = crm.login(REP_B, ["rep"])
    y = created_id(rep_b, body("Gospodarstwo K02 Y", m))
    before = crm.counts()

    on_another = create(rep_b, full_body("Gospodarstwo K02 nowe", n, "K02B"))
    on_own = create(rep_b, full_body("Gospodarstwo K02 nowe", m, "K02B"))
    on_another_again = create(rep_b, full_body("Gospodarstwo K02 nowe", p, "K02B"))

    assert on_another.status_code == 409, on_another.text
    assert on_another.content == NIP_TAKEN_BODY
    assert same_answer(on_another, on_own)
    assert same_answer(on_another, on_another_again)
    needles = (x, y, REP_A, REP_B, *MARKERS, *spellings(n), *spellings(m))
    for answer in (on_another, on_own, on_another_again):
        assert names_nothing(answer, *needles) == []
    assert crm.counts() == before


def test_k02_contrast_the_same_body_with_an_untaken_nip_is_stored(crm: Crm) -> None:
    n, free = nips.valid_nip(32101), nips.valid_nip(32404)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, {**X_BODY, "tax_id": n})
    rep_b = crm.login(REP_B, ["rep"])
    refused = create(rep_b, full_body("Gospodarstwo K02 nowe", n, "K02B"))
    stored = create(rep_b, full_body("Gospodarstwo K02 nowe", free, "K02B"))
    assert refused.status_code == 409, refused.text
    assert stored.status_code == 201, stored.text
    assert refused.content != stored.content


def test_k02_a_rep_with_no_customers_gets_the_same_refusal(crm: Crm) -> None:
    n = nips.valid_nip(32101)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, {**X_BODY, "tax_id": n})
    rep_b = crm.login(REP_B, ["rep"])
    created_id(rep_b, body("Gospodarstwo K02 Y", nips.valid_nip(32202)))
    with_customers = create(rep_b, full_body("Gospodarstwo K02 nowe", n, "K02B"))
    rep_c = crm.login(REP_C, ["rep"])
    without = create(rep_c, full_body("Gospodarstwo K02 nowe", n, "K02B"))
    assert with_customers.status_code == 409, with_customers.text
    assert same_answer(with_customers, without)
