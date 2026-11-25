"""EKO-3-03 K-01 (CUS-6; ADR-0002 *NIP uniqueness*; G-8 A): a create whose Polish NIP, after the
EKO-3-02 normalisation, equals any stored customer's NIP is refused, whoever owns that customer,
and stores nothing. The scenarios cross owners: a test in which one rep creates both customers
would also pass under uniqueness per owner.

The spelling edges replace EKO-3-02's four-spellings test (G-8 A): each accepted spelling of a
taken NIP collides. Every NIP is synthetic and built at run time.
"""

import uuid
from typing import Any

import httpx
import pytest

from tests.runtime.eko301.conftest import REP_A, REP_B, Crm, create, created_id
from tests.runtime.eko303.conftest import (
    NIP_TAKEN,
    body,
    full_body,
    holders,
    stored_customer,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime


def pl_written(nip: str) -> str:
    """`PL` and a space, then the NIP's own digits hyphenated 3-3-2-2."""
    return "PL " + nips.hyphenated(nip)


def refused(response: httpx.Response) -> bool:
    return response.status_code == 409 and bool(response.json() == NIP_TAKEN)


def test_k01_a_nip_another_reps_customer_holds_is_refused_and_nothing_is_stored(
    crm: Crm,
) -> None:
    nip = nips.valid_nip(30101)
    rep_a = crm.login(REP_A, ["rep"])
    held = created_id(rep_a, body("Gospodarstwo K01 A", nip))
    before, row_before = crm.counts(), stored_customer(crm, held)

    rep_b = crm.login(REP_B, ["rep"])
    answer = create(rep_b, full_body("Gospodarstwo K01 B", pl_written(nip)))
    assert answer.status_code != 201, answer.text
    assert refused(answer), answer.text
    assert crm.counts() == before
    assert stored_customer(crm, held) == row_before

    again = create(rep_a, body("Gospodarstwo K01 A drugi", nip))
    assert refused(again), again.text
    assert crm.counts() == before
    assert holders(crm, nip) == [(uuid.UUID(held), REP_A)]


def test_k01_contrast_the_same_body_with_an_untaken_nip_is_stored(crm: Crm) -> None:
    nip, other = nips.valid_nip(30101), nips.valid_nip(30202)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, body("Gospodarstwo K01 A", nip))
    before = crm.counts()

    rep_b = crm.login(REP_B, ["rep"])
    answer = create(rep_b, full_body("Gospodarstwo K01 B", pl_written(other)))
    assert answer.status_code == 201, answer.text
    assert crm.counts() == {
        "customer": before["customer"] + 1,
        "customer_contact": before["customer_contact"] + 2,
    }


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(lambda n: n, id="plain"),
        pytest.param(nips.hyphenated, id="hyphenated"),
        pytest.param(nips.spaced, id="spaced"),
        pytest.param(lambda n: "pl" + n, id="lower-case-pl"),
        pytest.param(lambda n: "PL" + n, id="upper-case-pl"),
        pytest.param(lambda n: "   " + n + "  ", id="surrounding-spaces"),
        pytest.param(lambda n: n[:5] + " " * 22 + n[5:], id="32-characters-as-sent"),
        pytest.param(pl_written, id="pl-space-hyphenated"),
    ],
)
def test_k01_every_accepted_spelling_of_a_taken_nip_collides(crm: Crm, spelling: Any) -> None:
    nip = nips.valid_nip(30303)
    written = spelling(nip)
    assert len(written) <= 32
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, body("Gospodarstwo K01 A", nip))
    before = crm.counts()
    rep_b = crm.login(REP_B, ["rep"])
    answer = create(rep_b, full_body("Gospodarstwo K01 B", written))
    assert refused(answer), (written, answer.text)
    assert crm.counts() == before


def test_k01_a_33_character_spelling_gets_the_same_422_whether_the_nip_is_taken(
    crm: Crm,
) -> None:
    taken, untaken = nips.valid_nip(30404), nips.valid_nip(30505)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, body("Gospodarstwo K01 A", taken))
    before = crm.counts()
    rep_b = crm.login(REP_B, ["rep"])
    answers = []
    for nip in (taken, untaken):
        spelling = nip[:5] + " " * 23 + nip[5:]
        assert len(spelling) == 33
        answers.append(create(rep_b, body("Gospodarstwo K01 B", spelling)))
    on_taken, on_untaken = answers
    assert on_taken.status_code == 422, on_taken.text
    assert [tuple(e["loc"]) for e in on_taken.json()["detail"]] == [("body", "tax_id")]
    assert on_taken.content == on_untaken.content
    assert crm.counts() == before


def test_k01_a_malformed_body_with_a_taken_nip_gets_only_its_own_422(crm: Crm) -> None:
    taken, untaken = nips.valid_nip(30606), nips.valid_nip(30707)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, body("Gospodarstwo K01 A", taken))
    before = crm.counts()
    rep_b = crm.login(REP_B, ["rep"])
    on_taken = create(rep_b, body("Gospodarstwo K01 B", taken, postal_code="00950"))
    on_untaken = create(rep_b, body("Gospodarstwo K01 B", untaken, postal_code="00950"))
    assert on_taken.status_code == 422, on_taken.text
    assert [tuple(e["loc"]) for e in on_taken.json()["detail"]] == [("body", "postal_code")]
    assert on_taken.content == on_untaken.content
    assert crm.counts() == before


def test_k01_a_foreign_tax_id_of_the_same_digits_and_a_nip_do_not_block_each_other(
    crm: Crm,
) -> None:
    first, second = nips.valid_nip(30808), nips.valid_nip(30909)
    rep_a = crm.login(REP_A, ["rep"])
    rep_b = crm.login(REP_B, ["rep"])
    # A foreign customer first, then a Polish one with the same ten digits.
    created_id(rep_a, body("Ferma DE K01", first, country="DE"))
    assert create(rep_b, body("Gospodarstwo K01 PL", first)).status_code == 201
    # The reverse order.
    created_id(rep_a, body("Gospodarstwo K01 PL", second))
    assert create(rep_b, body("Ferma DE K01", second, country="DE")).status_code == 201
    assert crm.pg.rows(
        "SELECT count(*) FROM customer WHERE nip IN (%s, %s) OR foreign_tax_id IN (%s, %s)",
        (first, second, first, second),
    ) == [(4,)]


def test_k01_creates_without_a_nip_or_with_one_foreign_tax_id_are_all_stored(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    rep_b = crm.login(REP_B, ["rep"])
    for rep in (rep_a, rep_b):
        assert create(rep, body("Gospodarstwo bez NIP")).status_code == 201
        assert create(rep, body("Ferma DE", "DE-K01-303", country="DE")).status_code == 201
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE nip IS NULL") == [(4,)]
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE foreign_tax_id = 'DE-K01-303'") == [
        (2,)
    ]


def test_k01_a_create_repeated_after_a_timeout_is_refused_not_stored_twice(crm: Crm) -> None:
    nip = nips.valid_nip(31010)
    rep_a = crm.login(REP_A, ["rep"])
    sent = full_body("Gospodarstwo K01 powtorka", nip)
    first = create(rep_a, sent)
    assert first.status_code == 201, first.text
    before = crm.counts()
    repeated = create(rep_a, sent)
    assert refused(repeated), repeated.text
    assert crm.counts() == before
    assert holders(crm, nip) == [(uuid.UUID(first.json()["id"]), REP_A)]
