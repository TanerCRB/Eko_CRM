"""EKO-3-05 K-04, ADR-0004-C37 (EKO-3-05 addendum draft; gate-1 decision Q-1 A): revision 0007 adds
the customer's archived state as an expand step, and the published previous release keeps working
over it and over a rollback.

- Customers and contacts the previous release stored read back unchanged and active after the step.
- The previous backend keeps reading, listing and creating on the expanded schema; a customer it
  creates reads back `archived: false` from the head backend.
- Rollback leg: the head backend archives a customer, the previous backend serves again and its
  by-id read and list answer that customer (as active: the accepted, announced effect) and change
  nothing of it; when the head backend serves again the customer is still archived, its
  `archived_at`, every field and every contact unchanged.

The previous backend is found as ADR-0004-C13's previous-release half finds it
(`tests/support/releases.py`) and run by digest. These tests run while that release's head is below
0007 and at least 0004, the first head with customer operations: once a release holding 0007 is
published, the step lies behind the previous release and they skip, naming why. A missing release,
an older head or a non-numeric one fails. Every customer value is synthetic (ADR-0005).
"""

import os
from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.conftest import Started
from tests.runtime.lab import SHIPPED_HEAD, Lab, PsqlSession, docker
from tests.runtime.test_eko302_k06_expand_on_customer import (
    OLD_ROWS,
    call,
    created,
    head_backend,
    image_head,
    listed,
    read,
    rep_session,
)
from tests.support.releases import (
    CannotTell,
    c13_previous_backend,
    reach_from_environment,
    record_from_environment,
)

pytestmark = pytest.mark.previous_release

REVISION = "0007"
# Revision 0004 adds the customers; a release before it has no customer operation to keep working.
OLDEST_HEAD = "0004"
CUSTOMERS = "/api/customers"
SEEDED: dict[str, Any] = {
    "name": "Gospodarstwo Przed Archiwum",
    "contacts": [
        {"kind": "phone", "value": "+48601305701", "note": "Pan Testowy C37", "primary": True},
        {"kind": "email", "value": "przed-archiwum@farm.example.invalid"},
    ],
}
CONTROL: dict[str, Any] = {
    "name": "Gospodarstwo Kontrolne C37",
    "contacts": [{"kind": "phone", "value": "+48601305702", "primary": True}],
}
# Every column of both owned tables, as PostgreSQL holds them, whichever revision added it.
CUSTOMER_ROWS = "SELECT row_to_json(c)::text FROM customer c ORDER BY c.id"
CONTACT_ROWS = (
    "SELECT row_to_json(k)::text FROM customer_contact k ORDER BY k.customer_id, k.position"
)


@pytest.fixture(scope="module")
def previous_backend() -> str:
    try:
        found = c13_previous_backend(
            record_from_environment(), reach_from_environment(), os.environ.get("RELEASE_TAG")
        )
    except CannotTell as error:
        pytest.fail(f"C37: the previous release could not be read: {error}")
    if found is None:
        pytest.fail("C37: no published release is reachable from main")
    docker("pull", "--quiet", found, timeout=600)
    return found


@pytest.fixture(scope="module")
def previous_head(previous_backend: str) -> str:
    head = image_head(previous_backend)
    if not head.isdigit():
        pytest.fail(f"C37: the previous release's head {head!r} is not a numeric revision")
    if int(head) >= int(REVISION):
        pytest.skip(f"the previous release's head is {head}: the {REVISION} step is behind it")
    if int(head) < int(OLDEST_HEAD):
        pytest.fail(
            f"C37: the previous release's head is {head}, older than {OLDEST_HEAD}: it has no "
            "customer operations to keep working"
        )
    return head


@pytest.fixture(scope="module")
def c37_lab(
    running: Started,
    tmp_path_factory: pytest.TempPathFactory,
    previous_backend: str,
    previous_head: str,
) -> Iterator[Lab]:
    """A `Lab` over the dev profile; afterwards the database is at the head again and the head
    backend serves, as the rest of the session expects."""
    composition = running.composition
    prober = f"{composition.project}-eko305-prober"
    composition.compose(
        "run", "-d", "--no-deps", "--name", prober, "--entrypoint", "sleep", "migrate",
        "infinity",
    )  # fmt: skip
    monitor = PsqlSession(composition, name="eko-test-eko305-monitor")
    shipped = composition.inspect("backend")["Config"]["Image"]
    lab = Lab(composition, tmp_path_factory.mktemp("eko305-c37"), shipped, prober, monitor)
    try:
        yield lab
    finally:
        try:
            code, logs = lab.run_migrate()
            assert code == 0, logs
            head_backend(lab)
        finally:
            monitor.close()
            docker("rm", "-f", prober, check=False)


def previous_serves(lab: Lab, previous: str) -> None:
    """The previous release's backend on `backend`; the schema is left where it is."""
    serving = lab._with_image("backend", previous)
    serving.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
    lab.wait_for_health("200", 90)
    assert lab.composition.inspect("backend")["Config"]["Image"] == previous


def previous_on_its_head(lab: Lab, previous: str, head: str) -> None:
    """An empty database migrated by the previous release, which then serves."""
    lab.reset()
    code, logs = lab.run_migrate(previous)
    assert code == 0, logs
    assert lab.versions() == [head]
    previous_serves(lab, previous)


def step_to_head(lab: Lab) -> None:
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.versions() == [SHIPPED_HEAD]


def stored(lab: Lab) -> tuple[list[list[str]], list[list[str]]]:
    return lab.sql(CUSTOMER_ROWS), lab.sql(CONTACT_ROWS)


def test_c37_rows_the_previous_release_stored_read_back_unchanged_and_active(
    c37_lab: Lab, previous_backend: str, previous_head: str
) -> None:
    lab = c37_lab
    previous_on_its_head(lab, previous_backend, previous_head)
    session = rep_session(lab)
    seeded = created(lab, session, SEEDED)
    by_id_before = read(lab, session, seeded["id"]).json()
    rows_before = lab.sql(OLD_ROWS)
    assert len(rows_before) == 2

    step_to_head(lab)
    assert lab.sql(OLD_ROWS) == rows_before
    assert lab.sql("SELECT count(*) FROM customer WHERE archived_at IS NULL") == [["1"]]

    head_backend(lab)
    by_id_after = read(lab, session, seeded["id"]).json()
    assert by_id_after.pop("archived") is False
    assert {k: v for k, v in by_id_after.items() if k in by_id_before} == by_id_before
    assert listed(lab, session).json()["items"] == [
        {"id": seeded["id"], "name": SEEDED["name"], "country": "PL", "archived": False}
    ]


def test_c37_the_previous_backend_reads_lists_and_creates_on_the_expanded_schema(
    c37_lab: Lab, previous_backend: str, previous_head: str
) -> None:
    lab = c37_lab
    previous_on_its_head(lab, previous_backend, previous_head)
    session = rep_session(lab)
    seeded = created(lab, session, SEEDED)
    by_id_before = read(lab, session, seeded["id"]).content

    step_to_head(lab)
    assert lab.composition.inspect("backend")["Config"]["Image"] == previous_backend
    assert read(lab, session, seeded["id"]).content == by_id_before
    second = created(lab, session, CONTROL)
    assert "archived" not in second
    assert {item["id"] for item in listed(lab, session).json()["items"]} == {
        seeded["id"],
        second["id"],
    }
    assert lab.sql("SELECT count(*) FROM customer WHERE archived_at IS NULL") == [["2"]]

    # From the head backend, the previous backend's create reads back active.
    head_backend(lab)
    assert read(lab, session, second["id"]).json()["archived"] is False


def test_c37_rollback_leg_the_previous_backend_serves_an_archived_customer_and_changes_nothing(
    c37_lab: Lab, previous_backend: str, previous_head: str
) -> None:
    lab = c37_lab
    previous_on_its_head(lab, previous_backend, previous_head)
    session = rep_session(lab)
    archived = created(lab, session, SEEDED)
    control = created(lab, session, CONTROL)
    step_to_head(lab)
    head_backend(lab)
    answered = call(lab, session, "POST", f"{CUSTOMERS}/{archived['id']}/archive")
    assert answered.status_code == 200, answered.text[:500]
    assert answered.json()["archived"] is True
    after_archive = stored(lab)
    assert lab.sql("SELECT id::text FROM customer WHERE archived_at IS NOT NULL") == [
        [archived["id"]]
    ]

    # The rollback: the previous release's images serve the same, expanded schema.
    previous_serves(lab, previous_backend)
    by_id = read(lab, session, archived["id"]).json()
    assert (by_id["id"], by_id["name"]) == (archived["id"], SEEDED["name"])
    assert "archived" not in by_id
    assert {item["id"] for item in listed(lab, session).json()["items"]} == {
        archived["id"],
        control["id"],
    }
    assert stored(lab) == after_archive

    # The head backend serves again: still archived, every field and contact unchanged.
    head_backend(lab)
    assert stored(lab) == after_archive
    assert read(lab, session, archived["id"]).json()["archived"] is True
    assert read(lab, session, control["id"]).json()["archived"] is False
