"""EKO-3-01 K-03 mutation (3), QA: a create is one transaction, so a request that fails while its
contacts are written leaves neither the customer nor any contact behind.

Every value rule is checked before the handler runs, so no request the API accepts reaches the
store with a contact that will be refused, and the K-03 rejection tests pass even when the
customer is committed before its contacts. Here the refusal comes from the database itself: a
trigger planted for this test refuses one synthetic contact value, the last of three. The
contrast changes only that value, so the trigger is shown to refuse nothing else. Every value is
synthetic (ADR-0005).
"""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm, create, listed_ids

pytestmark = pytest.mark.runtime

REFUSED_VALUE = "+48601999001"
ACCEPTED_VALUE = "+48601999002"
PLANT = f"""
CREATE FUNCTION qa_eko301_refuse_contact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.value = '{REFUSED_VALUE}' THEN
        RAISE EXCEPTION 'planted refusal';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER qa_eko301_refuse_contact BEFORE INSERT ON customer_contact
    FOR EACH ROW EXECUTE FUNCTION qa_eko301_refuse_contact();
"""
REMOVE = """
DROP TRIGGER IF EXISTS qa_eko301_refuse_contact ON customer_contact;
DROP FUNCTION IF EXISTS qa_eko301_refuse_contact();
"""


def body(last_value: str) -> dict[str, Any]:
    return {
        "name": "Gospodarstwo Transakcja",
        "contacts": [
            {"kind": "phone", "value": "+48601999000", "primary": True},
            {"kind": "email", "value": "transakcja@farm.example.invalid"},
            {"kind": "phone", "value": last_value},
        ],
    }


@pytest.fixture
def refusing_database(crm: Crm) -> Iterator[None]:
    with crm.pg.connect() as connection:
        connection.execute(REMOVE)
        connection.execute(PLANT)
    try:
        yield
    finally:
        with crm.pg.connect() as connection:
            connection.execute(REMOVE)


def test_qa_k03_a_contact_refused_by_the_database_leaves_no_customer(
    crm: Crm, refusing_database: None
) -> None:
    rep = crm.login(REP_A, ["rep"])
    before_list, before_counts = listed_ids(rep), crm.counts()
    response = create(rep, body(REFUSED_VALUE))
    assert response.status_code == 503, response.text
    assert crm.counts() == before_counts
    assert listed_ids(rep) == before_list


def test_qa_k03_contrast_the_same_create_with_another_last_value_is_stored(
    crm: Crm, refusing_database: None
) -> None:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = create(rep, body(ACCEPTED_VALUE))
    assert response.status_code == 201, response.text
    assert crm.counts() == {
        "customer": before["customer"] + 1,
        "customer_contact": before["customer_contact"] + 3,
    }
