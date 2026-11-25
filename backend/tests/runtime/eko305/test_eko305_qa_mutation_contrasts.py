"""EKO-3-05, QA contrasts: three claims the developer's suites state but whose mutation survived
them, or that only a CI-only carrier guarded.

- K-03 M-k2 (ADR-0003-C40, "only this constraint is NIP-taken"): the developer's other-violation
  test collides on the contact insert, which runs after the `UPDATE` and outside its `except`, so
  the edit's constraint-name check was never reached. Here a unique index planted for the test
  is violated by the edit's own `UPDATE` of the customer row: it must stay 503 and change
  nothing, while the same edit with the planted index absent is stored.
- K-03 M-i (the replacement contacts are written in the customer's transaction): the developer's
  trigger fails the contact insert itself, so a transaction of its own for the contacts rolls back
  with it and nothing is left changed. Here a deferred constraint trigger planted for the test
  refuses the edit at its commit, after every statement ran: contacts written outside the
  customer's transaction would then stay replaced while the customer row is rolled back.
- K-04 M-p6 (head does not re-derive or clear the state when it starts): the C37 rollback leg
  needs the published previous release and runs only in CI. Here a second application is built
  and started over the same database after a customer was archived; the customer is still
  archived with its instant, and an active one is still active.

Every value is synthetic (ADR-0005); NIPs are built at run time (EKO-3-02 G-7 A).
"""

import inspect
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI

from tests.runtime.eko201.conftest import AppFactory, Browser, FakeClock
from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_B, Crm
from tests.runtime.eko305 import test_eko305_k06_one_change_changes_no_other_customer as k06
from tests.runtime.eko305.conftest import (
    archive,
    archived_at,
    customer,
    edit,
    email,
    others,
    phone,
    read,
    read_json,
    restore,
    snapshot,
    status_and_json,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

UNAVAILABLE = (503, {"detail": "temporarily unavailable"})
HELD_NAME = "Gospodarstwo Zajete QA305"
FREE_NAME = "Gospodarstwo Wolne QA305"
REFUSED_AT_COMMIT = "Gospodarstwo Odmowa Przy Zatwierdzeniu QA305"
ACCEPTED_AT_COMMIT = "Gospodarstwo Przyjete Przy Zatwierdzeniu QA305"

PLANT_INDEX = "CREATE UNIQUE INDEX qa_eko305_customer_name ON customer (name)"
REMOVE_INDEX = "DROP INDEX IF EXISTS qa_eko305_customer_name"

PLANT_COMMIT_REFUSAL = f"""
CREATE FUNCTION qa_eko305_refuse_at_commit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.name = '{REFUSED_AT_COMMIT}' THEN RAISE EXCEPTION 'planted refusal at commit'; END IF;
    RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER qa_eko305_refuse_at_commit AFTER UPDATE ON customer
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qa_eko305_refuse_at_commit();
"""
REMOVE_COMMIT_REFUSAL = """
DROP TRIGGER IF EXISTS qa_eko305_refuse_at_commit ON customer;
DROP FUNCTION IF EXISTS qa_eko305_refuse_at_commit();
"""


def stored(name: str, marker: str, seed: int) -> dict[str, Any]:
    return {
        "name": name,
        "street": f"ul. Stara {marker}",
        "postal_code": "05-805",
        "town": "Stara Wola",
        "tax_id": nips.valid_nip(seed),
        "contacts": [
            phone("+48601305901", f"Notatka {marker}", primary=True),
            email(f"stara-{marker.lower()}@farm.example.invalid"),
        ],
    }


def replaced(name: str) -> dict[str, Any]:
    """Every field and every contact changed, so a partial write is visible in the rows."""
    return {
        "name": name,
        "street": "ul. Nowa QA",
        "postal_code": "05-806",
        "town": "Nowa Wola",
        "voivodeship": "mazowieckie",
        "county": "Warszawa",
        "contacts": [email("nowa-qa305@farm.example.invalid", "Nowa notatka", primary=True)],
    }


def run_sql(crm: Crm, statement: str) -> None:
    with crm.pg.connect() as connection:
        connection.execute(statement)


# K-03 M-k2 --------------------------------------------------------------------------------------


@pytest.fixture
def planted_index(crm: Crm) -> Any:
    run_sql(crm, REMOVE_INDEX)
    run_sql(crm, PLANT_INDEX)
    yield
    run_sql(crm, REMOVE_INDEX)


def test_eko305_qa_k03_another_unique_violation_on_the_edits_own_update_is_503_and_changes_nothing(
    crm: Crm, planted_index: None
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, **stored(HELD_NAME, "HELD", 305910))
    target = customer(rep, **stored(FREE_NAME, "TARGET", 305920))
    before, counts = snapshot(crm), crm.counts()
    answer = edit(rep, target, replaced(HELD_NAME))
    assert status_and_json(answer) == UNAVAILABLE
    assert "existing_customer_id" not in answer.text
    assert snapshot(crm) == before
    assert crm.counts() == counts


def test_eko305_qa_k03_contrast_the_same_edit_without_the_planted_index_is_stored(
    crm: Crm,
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, **stored(HELD_NAME, "HELD", 305910))
    target = customer(rep, **stored(FREE_NAME, "TARGET", 305920))
    answer = edit(rep, target, replaced(HELD_NAME))
    assert answer.status_code == 200, answer.text
    assert read_json(rep, target)["name"] == HELD_NAME


# K-03 M-i ---------------------------------------------------------------------------------------


@pytest.fixture
def planted_commit_refusal(crm: Crm) -> Any:
    run_sql(crm, REMOVE_COMMIT_REFUSAL)
    run_sql(crm, PLANT_COMMIT_REFUSAL)
    yield
    run_sql(crm, REMOVE_COMMIT_REFUSAL)


def test_eko305_qa_k03_an_edit_refused_at_its_commit_leaves_the_contacts_with_the_row(
    crm: Crm, planted_commit_refusal: None
) -> None:
    rep = crm.login(REP_A, ["rep"])
    target = customer(rep, **stored(FREE_NAME, "COMMIT", 305930))
    before, counts = snapshot(crm), crm.counts()
    answer = edit(rep, target, replaced(REFUSED_AT_COMMIT))
    assert status_and_json(answer) == UNAVAILABLE
    assert snapshot(crm) == before
    assert crm.counts() == counts


def test_eko305_qa_k03_contrast_with_the_commit_refusal_planted_another_name_is_stored(
    crm: Crm, planted_commit_refusal: None
) -> None:
    rep = crm.login(REP_A, ["rep"])
    target = customer(rep, **stored(FREE_NAME, "COMMIT", 305930))
    before = snapshot(crm)
    answer = edit(rep, target, replaced(ACCEPTED_AT_COMMIT))
    assert answer.status_code == 200, answer.text
    assert snapshot(crm) != before
    found = read_json(rep, target)
    assert found["name"] == ACCEPTED_AT_COMMIT
    assert [c["value"] for c in found["contacts"]] == ["nowa-qa305@farm.example.invalid"]


# K-04 M-p6 --------------------------------------------------------------------------------------


def test_eko305_qa_k04_a_head_backend_started_again_keeps_the_archived_state(
    crm: Crm,
    make_app: AppFactory,
    browser_for: Callable[[FastAPI], Browser],
    clock: FakeClock,
) -> None:
    rep = crm.login(REP_A, ["rep"])
    archived = customer(rep, **stored(FREE_NAME, "ARCHIVED", 305940))
    active = customer(rep, **stored(HELD_NAME, "ACTIVE", 305950))
    assert archive(rep, archived).status_code == 200
    instant = archived_at(crm, archived)
    assert instant is not None
    before = snapshot(crm)

    # A second application over the same database, started as the head backend starts.
    again = make_app()
    again.state.clock = clock
    restarted = Crm(again, crm.pg, crm.stub, browser_for)
    rep_again = restarted.login(REP_A, ["rep"])

    assert snapshot(crm) == before
    assert archived_at(crm, archived) == instant
    assert read_json(rep_again, archived)["archived"] is True
    assert read_json(rep_again, active)["archived"] is False
    assert read(rep_again, archived).status_code == 200


# K-06 M-t ---------------------------------------------------------------------------------------
# The developer's K-06 edit body sets a NIP, so an edit that lost its customer-id condition writes
# that NIP onto every customer in the scope and the unique constraint refuses it (409): the test
# then fails on the status, through ADR-0002's constraint, not on the rows of the other customers.
# Here the same edits carry no NIP, so only the per-customer condition keeps the siblings intact.


def nipless_body() -> dict[str, Any]:
    return {
        "name": "Gospodarstwo Po Zmianie Bez NIP QA305",
        "town": "Nowa Wola QA305",
        "contacts": [phone("+48601305961", primary=True)],
    }


@pytest.fixture
def k06_scene(crm: Crm, clock: FakeClock) -> dict[str, Any]:
    """The K-06 scene: the target, a twin sibling of the same owner with its own NIP, a sibling
    archived at an earlier instant, and a customer of another rep."""
    found: dict[str, Any] = inspect.unwrap(k06.scene)(crm, clock)
    return found


@pytest.mark.parametrize("caller", ["rep_a", "manager"])
def test_eko305_qa_k06_an_edit_without_a_nip_changes_no_other_row(
    crm: Crm, k06_scene: dict[str, Any], caller: str
) -> None:
    scene = k06_scene
    target = scene["target"]
    before = snapshot(crm)
    response = edit(scene[caller], target, nipless_body())
    assert response.status_code == 200, response.text
    after = snapshot(crm)
    assert others(after, target) == others(before, target)
    # The target's own row did change, so a no-op cannot pass.
    assert after[0][target] != before[0][target]
    assert after[0][target][9] is None


# K-06 M-v ---------------------------------------------------------------------------------------
# The K-06 scene archives its archived sibling through `POST …/archive`, so an archive that lost
# its customer-id condition already archives the target and the twin while the scene is built:
# every later step then meets an archived target (a 409 or a no-op), and the kill does not come
# from the comparison of the other rows. Here the archived sibling is set archived in the
# database directly, so the scene does not run the operation under test.

EARLIER = "2026-11-01 07:00:00+00"


@pytest.fixture
def sql_scene(crm: Crm) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    scene = {
        "rep_a": rep_a,
        "manager": crm.login(MANAGER, ["manager"]),
        "target": customer(rep_a, **stored(FREE_NAME, "TARGET", 305920)),
        "sibling": customer(rep_a, **stored(FREE_NAME, "SIBLING", 305930)),
        "archived_sibling": customer(rep_a, **stored(HELD_NAME, "ASLEEP", 305940)),
        "other_rep": customer(rep_b, **stored(FREE_NAME, "OTHER", 305950)),
    }
    with crm.pg.connect() as connection:
        connection.execute(
            "UPDATE customer SET archived_at = %s WHERE id = %s",
            (EARLIER, scene["archived_sibling"]),
        )
    return scene


@pytest.mark.parametrize("caller", ["rep_a", "manager"])
def test_eko305_qa_k06_archive_and_restore_change_no_other_row(
    crm: Crm, sql_scene: dict[str, Any], caller: str
) -> None:
    target = sql_scene["target"]
    for step in (archive, restore):
        before = snapshot(crm)
        response = step(sql_scene[caller], target)
        assert response.status_code == 200, response.text
        after = snapshot(crm)
        assert others(after, target) == others(before, target), step.__name__
        assert after[0][target] != before[0][target], step.__name__
    assert archived_at(crm, sql_scene["sibling"]) is None
    assert archived_at(crm, sql_scene["archived_sibling"]) is not None
