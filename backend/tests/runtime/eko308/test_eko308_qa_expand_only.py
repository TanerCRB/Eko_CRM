"""EKO-3-08 QA, revision 0006 as an expand step (ADR-0002, ADR-0004 *Expand -> deploy -> contract*):
the previous release, which writes no display-name copy, still writes its rows on the expanded
schema. Its writes are made here as it makes them, in SQL, for subjects that hold no copy: a
session, a customer with a contact. No carrier ran the previous release against 0006 (the
composition-level previous-release test steps 0004 -> 0005 only), so a constraint 0006 adds on a
table the previous release writes, e.g. a foreign key from `customer.owner_subject` to the copy,
was found only by model/migration drift, not by its effect.

Only `pg` and the customer cleanup are used: no fixture here truncates the copy table, so a
constraint pointing at it cannot turn this test into a setup error. Every value is synthetic.
"""

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from tests.runtime.eko308.conftest import copies, copy_table_exists
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

NO_COPY = "5a1e0308-0000-4000-8000-0000000000e1"
AT = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)


def previous_release_writes(pg: Postgres, subject: str) -> uuid.UUID:
    customer = uuid.uuid4()
    with pg.connect() as connection:
        connection.execute(
            "INSERT INTO app_session (session_hash, subject, tokens, access_expires_at, "
            "created_at, last_used_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (f"qa-0006-{customer}", subject, b"sealed", AT, AT, AT),
        )
        connection.execute(
            "INSERT INTO customer (id, name, country, owner_subject) VALUES (%s, %s, 'PL', %s)",
            (customer, "Ferma Poprzedniego Wydania", subject),
        )
        connection.execute(
            "INSERT INTO customer_contact (id, customer_id, position, kind, value, note, "
            "is_primary) VALUES (%s, %s, 0, 'phone', '+48601308308', NULL, true)",
            (uuid.uuid4(), customer),
        )
    return customer


def test_qa_0006_the_previous_releases_writes_succeed_for_a_subject_with_no_copy(
    pg: Postgres, clean_customers: None
) -> None:
    assert copy_table_exists(pg), "revision 0006 is not applied: the test would be vacuous"
    assert NO_COPY not in copies(pg)
    try:
        customer = previous_release_writes(pg, NO_COPY)
    except psycopg.Error as exc:
        pytest.fail(f"the 0006 schema refuses a previous-release write: {type(exc).__name__}")
    try:
        assert pg.rows("SELECT owner_subject FROM customer WHERE id = %s", (customer,)) == [
            (NO_COPY,)
        ]
    finally:
        with pg.connect() as connection:
            connection.execute("DELETE FROM app_session WHERE subject = %s", (NO_COPY,))


def test_qa_0006_contrast_a_write_the_0006_schema_forbids_is_refused(pg: Postgres) -> None:
    """The same harness reports a refused write as a failure: a second copy of one subject."""
    row = (NO_COPY, None, True, AT)
    insert = "INSERT INTO staff_display_name VALUES (%s, %s, %s, %s)"
    try:
        with pg.connect() as connection:
            connection.execute(insert, row)
        with pytest.raises(psycopg.errors.UniqueViolation), pg.connect() as connection:
            connection.execute(insert, row)
    finally:
        with pg.connect() as connection:
            connection.execute("DELETE FROM staff_display_name WHERE subject = %s", (NO_COPY,))
