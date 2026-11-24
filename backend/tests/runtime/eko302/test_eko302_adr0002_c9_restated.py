"""EKO-3-02, ADR-0002-C9 (restated for the interval until EKO-3-03 by the ADR-0002 addendum draft
of EKO-3-02, accepted at gate 1, Q-1 A; as written again since EKO-3-03's revision 0007, G-8 A):
inserting straight through SQL, past the services, a `nip` that is not ten digits fails with a
check violation (SQLSTATE 23514); two customers without a `nip` are both stored; two with the
same `foreign_tax_id` are both stored; and a second customer with an existing `nip` fails with a
unique violation (SQLSTATE 23505).

Every NIP is synthetic and built at run time (G-7 A).
"""

import uuid
from typing import Any

import psycopg
import pytest

from tests.runtime.eko301.conftest import REP_A, Crm
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

INSERT = (
    "INSERT INTO customer (id, name, country, owner_subject, nip, foreign_tax_id) "
    "VALUES (%s, 'Gospodarstwo C9', %s, %s, %s, %s)"
)


def insert(crm: Crm, country: str, nip: Any, foreign: Any) -> None:
    with crm.pg.connect() as connection:
        connection.execute(INSERT, (uuid.uuid4(), country, REP_A, nip, foreign))


@pytest.mark.parametrize(
    "nip",
    [
        pytest.param(lambda: "PL" + nips.valid_nip(1), id="pl-prefix"),
        pytest.param(lambda: "DE123456789", id="foreign-value"),
        pytest.param(lambda: nips.valid_nip(1)[:9], id="nine-digits"),
        pytest.param(lambda: nips.valid_nip(1) + "0", id="eleven-digits"),
        pytest.param(lambda: nips.hyphenated(nips.valid_nip(1)), id="hyphenated"),
        pytest.param(lambda: "", id="empty"),
        pytest.param(
            lambda: nips.other_digits(nips.valid_nip(1), 0x0660),
            id="arabic-indic-digits",
        ),
    ],
)
def test_c9_a_nip_that_is_not_ten_digits_is_a_check_violation(crm: Crm, nip: Any) -> None:
    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(crm, "PL", nip(), None)
    assert raised.value.sqlstate == "23514"
    assert crm.counts()["customer"] == 0


def test_c9_contrast_ten_digits_are_stored(crm: Crm) -> None:
    insert(crm, "PL", nips.valid_nip(1), None)
    assert crm.counts()["customer"] == 1


def test_c9_two_customers_without_a_nip_are_both_stored(crm: Crm) -> None:
    insert(crm, "PL", None, None)
    insert(crm, "PL", None, None)
    assert crm.counts()["customer"] == 2


def test_c9_two_customers_with_the_same_foreign_tax_id_are_both_stored(crm: Crm) -> None:
    insert(crm, "DE", None, "DE123456789")
    insert(crm, "DE", None, "DE123456789")
    assert crm.counts()["customer"] == 2


def test_c9_restated_a_second_customer_with_an_existing_nip_is_stored(crm: Crm) -> None:
    """The interval ended with EKO-3-03 (G-8 A): the second customer is refused, not stored."""
    nip = nips.valid_nip(1)
    insert(crm, "PL", nip, None)
    with pytest.raises(psycopg.errors.UniqueViolation) as raised:
        insert(crm, "PL", nip, None)
    assert raised.value.sqlstate == "23505"
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE nip = %s", (nip,)) == [(1,)]
