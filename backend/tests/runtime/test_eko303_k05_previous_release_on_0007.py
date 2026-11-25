"""EKO-3-03 K-05 (4) (ADR-0004-C13 previous-release half; the gate-1 addendum draft, section 1;
G-4 A, G-7 A): the previous published release starts on a database migrated to revision 0007 and
creates and reads customers there, each one stored with `nip` NULL, so the unique constraint does
not touch it.

The previous release is found as the C13 previous-release half finds it (`tests/support/
releases.py`) and run by digest. The deviation of gate 1 holds only while every published
release's head is an ancestor of 0005: a previous release at 0005 or 0006 means it lapsed, and
this fails, naming why. Once a release holding 0007 is published the step lies behind it and this
skips. A release older than 0004 has no customer operations; that fails too.

The dev profile (`running`) supplies Keycloak, so each request carries a real session made by a
real login through the proxy. Every customer value is synthetic (ADR-0005).
"""

import os
from collections.abc import Iterator

import pytest

from tests.runtime.conftest import Started
from tests.runtime.lab import Lab, PsqlSession, docker
from tests.runtime.test_eko302_k06_expand_on_customer import (
    SEEDED,
    created,
    head_backend,
    image_head,
    listed,
    previous_on_0004,
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

PREVIOUS_HEAD = "0004"
LAPSED = ("0005", "0006")
REVISION = "0007"
NIP_CONSTRAINT = (
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conrelid = 'customer'::regclass AND conname = 'uq_customer_nip'"
)


@pytest.fixture(scope="module")
def previous_backend() -> str:
    try:
        found = c13_previous_backend(
            record_from_environment(), reach_from_environment(), os.environ.get("RELEASE_TAG")
        )
    except CannotTell as error:
        pytest.fail(f"K-05: the previous release could not be read: {error}")
    if found is None:
        pytest.fail("K-05: no published release is reachable from main")
    docker("pull", "--quiet", found, timeout=600)
    return found


@pytest.fixture(scope="module")
def step(previous_backend: str) -> str:
    head = image_head(previous_backend)
    if not head.isdigit():
        pytest.fail(
            f"K-05: the previous release's head {head!r} is not a numeric revision: could not tell"
        )
    if head in LAPSED:
        pytest.fail(
            f"K-05: the previous release's head is {head}: a release holding 0005 or 0006 but "
            "not 0007 was published, so the gate-1 deviation of EKO-3-03 lapsed; the task goes "
            "back to gate 1"
        )
    if int(head) >= int(REVISION):
        pytest.skip(f"the previous release's head is {head}: the {REVISION} step is behind it")
    if head != PREVIOUS_HEAD:
        pytest.fail(
            f"K-05: the previous release's head is {head}, not {PREVIOUS_HEAD}: it has no "
            "customer operations to keep working"
        )
    return previous_backend


@pytest.fixture(scope="module")
def contract_lab(
    running: Started, tmp_path_factory: pytest.TempPathFactory, step: str
) -> Iterator[Lab]:
    """A `Lab` over the dev profile; afterwards the database is at the head again and the head
    backend serves, as the rest of the session expects."""
    composition = running.composition
    prober = f"{composition.project}-eko303-prober"
    composition.compose(
        "run", "-d", "--no-deps", "--name", prober, "--entrypoint", "sleep", "migrate",
        "infinity",
    )  # fmt: skip
    monitor = PsqlSession(composition, name="eko-test-eko303-monitor")
    shipped = composition.inspect("backend")["Config"]["Image"]
    lab = Lab(composition, tmp_path_factory.mktemp("eko303-k05"), shipped, prober, monitor)
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


def test_k05_the_previous_release_creates_and_reads_customers_on_0007(
    contract_lab: Lab, step: str
) -> None:
    lab = contract_lab
    previous_on_0004(lab, step)
    session = rep_session(lab)
    seeded = created(lab, session, SEEDED)
    by_id_before = read(lab, session, seeded["id"]).content

    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.versions() == [REVISION]
    assert lab.sql(NIP_CONSTRAINT) == [["UNIQUE (nip)"]]
    assert lab.composition.inspect("backend")["Config"]["Image"] == step

    assert read(lab, session, seeded["id"]).content == by_id_before
    second = created(lab, session, {**SEEDED, "name": "Gospodarstwo Po Ograniczeniu"})
    third = created(lab, session, {**SEEDED, "name": "Gospodarstwo Po Ograniczeniu Drugie"})
    for customer in (second, third):
        assert read(lab, session, customer["id"]).json() == customer
    assert {item["id"] for item in listed(lab, session).json()["items"]} == {
        seeded["id"],
        second["id"],
        third["id"],
    }
    # Every customer the previous release stores has no NIP, so NULLs stay distinct for it.
    assert lab.sql("SELECT count(*) FROM customer WHERE nip IS NULL") == [["3"]]
