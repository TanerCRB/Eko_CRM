"""EKO-3-02 K-06 (ADR-0002 and ADR-0004 *Expand → deploy → contract*; ADR-0004-C13, C26): revision
0005 is an expand step on `customer`, a table that holds rows. Customers stored before it read back
unchanged with every new field not given; the previous backend keeps answering customer reads and
creates on the expanded schema; and while a conflicting lock blocks the step, the previous backend
still answers by-id and list requests through the product endpoint.

The previous backend is the previous published release (gate 1 of EKO-3-02, Q-2 B), found as the
C13 previous-release half finds it (`tests/support/releases.py`) and run by digest. The step under
test is 0004 → 0005, so these tests run only while that release's head is 0004: once a release
holding 0005 is published, the step lies behind the previous release and they skip, naming why. A
previous release older than 0004 has no customer operations; that fails, since Q-2 B requires the
release to be published before this task's CI runs.

The dev profile (`running`) supplies Keycloak, so each rep request carries a real session made by
a real login through the proxy, as a rep account of the test's own; the shared composition is left
on its own head images, never rebuilt. Every customer value is synthetic (ADR-0005).
"""

import json
import os
import secrets
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from tests.runtime import eko201_login as app
from tests.runtime import eko202_live as live
from tests.runtime.conftest import Started
from tests.runtime.keycloak_client import RealmClient
from tests.runtime.lab import Lab, PsqlSession, docker
from tests.runtime.test_adr0004_c26_lock_timeout import (
    LOCK_TIMEOUT,
    MARGIN,
    TOLERANCE,
    granted,
    waits_for_a_table_lock,
)
from tests.support.releases import (
    CannotTell,
    c13_previous_backend,
    reach_from_environment,
    record_from_environment,
)

pytestmark = pytest.mark.previous_release

STEP_BASE = "0004"
HEAD = "0005"
NEW_FIELDS = ("street", "postal_code", "town", "voivodeship", "county", "tax_id")
CUSTOMERS = "/api/customers"
AT_ONCE = 1.0
SEEDED = {
    "name": "Gospodarstwo Sprzed Zmiany",
    "contacts": [
        {"kind": "phone", "value": "+48601302302", "note": "Pan Testowy", "primary": True},
        {"kind": "email", "value": "przed-zmiana@farm.example.invalid"},
    ],
}
ADDRESSED = {
    "name": "Gospodarstwo Po Zmianie",
    "street": "ul. Polna 6",
    "postal_code": "00-950",
    "town": "Warszawa",
    "voivodeship": "mazowieckie",
    "county": "Warszawa",
}
OLD_ROWS = (
    "SELECT c.id, c.name, c.country, c.owner_subject, k.position, k.kind, k.value, k.note, "
    "k.is_primary FROM customer c LEFT JOIN customer_contact k ON k.customer_id = c.id "
    "ORDER BY c.id, k.position"
)
NEW_COLUMNS = (
    "SELECT street, postal_code, town, voivodeship, county, nip, foreign_tax_id FROM customer"
)


@pytest.fixture(scope="module")
def previous_backend() -> str:
    try:
        found = c13_previous_backend(
            record_from_environment(), reach_from_environment(), os.environ.get("RELEASE_TAG")
        )
    except CannotTell as error:
        pytest.fail(f"K-06: the previous release could not be read: {error}")
    if found is None:
        pytest.fail("K-06 (Q-2 B): no published release is reachable from main")
    docker("pull", "--quiet", found, timeout=600)
    return found


def image_head(image: str) -> str:
    result = docker("run", "--rm", "--network", "none", image, "alembic", "heads", check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    [line] = result.stdout.strip().splitlines()
    return line.split()[0]


@pytest.fixture(scope="module")
def step(previous_backend: str) -> str:
    head = image_head(previous_backend)
    if not head.isdigit():
        pytest.fail(
            f"K-06: the previous release's head {head!r} is not a numeric revision: could not tell"
        )
    if int(head) >= int(HEAD):
        pytest.skip(f"the previous release's head is {head}: the {HEAD} step is behind it")
    if head != STEP_BASE:
        pytest.fail(
            f"K-06 (Q-2 B): the previous release's head is {head}, not {STEP_BASE}; a release "
            "containing EKO-3-01 must be published before this task's CI runs"
        )
    return previous_backend


@pytest.fixture(scope="module")
def expand_lab(
    running: Started, tmp_path_factory: pytest.TempPathFactory, step: str
) -> Iterator[Lab]:
    """A `Lab` over the dev profile; afterwards the database is at the head again and the head
    backend serves, as the rest of the session expects."""
    composition = running.composition
    prober = f"{composition.project}-eko302-prober"
    composition.compose(
        "run", "-d", "--no-deps", "--name", prober, "--entrypoint", "sleep", "migrate",
        "infinity",
    )  # fmt: skip
    monitor = PsqlSession(composition, name="eko-test-eko302-monitor")
    shipped = composition.inspect("backend")["Config"]["Image"]
    lab = Lab(composition, tmp_path_factory.mktemp("eko302-k06"), shipped, prober, monitor)
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


def head_backend(lab: Lab) -> None:
    """The session's own head image back on `backend`, never a rebuild of it: `backend` has
    `pull_policy: build`, so a plain `up` rebuilds the tag the session's worker and migrate run."""
    composition = lab.composition
    composition.compose("up", "-d", "--no-deps", "--no-build", "--force-recreate", "backend")
    lab.wait_for_health("200", 90)
    assert composition.inspect("backend")["Image"] == composition.inspect("worker")["Image"]


def previous_on_0004(lab: Lab, previous: str) -> None:
    """An empty database migrated by the previous release, which then serves."""
    lab.reset()
    code, logs = lab.run_migrate(previous)
    assert code == 0, logs
    assert lab.versions() == [STEP_BASE]
    serving = lab._with_image("backend", previous)
    serving.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
    lab.wait_for_health("200", 90)
    assert lab.composition.inspect("backend")["Config"]["Image"] == previous


def rep_session(lab: Lab) -> str:
    """A real login as a rep account of this call's own. A shared account (`login`) may hold an
    OTP credential a browser enrolled earlier in the session, whose secret this process never
    saw; Keycloak then stops on its code page."""
    composition = lab.composition
    username, password = f"eko302-k06-{secrets.token_hex(4)}", live.new_password()
    live.Realm(composition).create_account(username, password, ["rep"])
    browser = RealmClient(composition, "eko", listener="auth")
    try:
        return app.login(composition, browser, username, password)
    finally:
        browser.close()


def call(lab: Lab, session: str, method: str, path: str, body: Any = None) -> httpx.Response:
    """A rep's request to the serving backend, through the proxy's application listener."""
    env = lab.composition.env
    host = env["APP_HOST"]
    url = httpx.URL(
        scheme="https", host="127.0.0.1", port=int(env["PROXY_HTTPS_PORT"]), raw_path=path.encode()
    )
    headers = {"Host": host, "Cookie": f"{app.SESSION_COOKIE}={session}"}
    if method != "GET":
        headers["Origin"] = app.app_origin(lab.composition)
    with httpx.Client(verify=False, timeout=30, follow_redirects=False) as client:
        request = client.build_request(method, url, headers=headers, json=body)
        request.extensions["sni_hostname"] = host
        return client.send(request)


def created(lab: Lab, session: str, body: dict[str, Any]) -> dict[str, Any]:
    response = call(lab, session, "POST", CUSTOMERS, body)
    assert response.status_code == 201, response.text[:500]
    answer: dict[str, Any] = response.json()
    return answer


def read(lab: Lab, session: str, customer_id: str) -> httpx.Response:
    response = call(lab, session, "GET", f"{CUSTOMERS}/{customer_id}")
    assert response.status_code == 200, response.text[:500]
    return response


def listed(lab: Lab, session: str) -> httpx.Response:
    response = call(lab, session, "GET", CUSTOMERS)
    assert response.status_code == 200, response.text[:500]
    return response


def without_new_fields(answer: dict[str, Any]) -> dict[str, Any]:
    assert all(answer[name] is None for name in NEW_FIELDS), answer
    return {k: v for k, v in answer.items() if k not in NEW_FIELDS}


def test_k06_existing_customers_read_back_unchanged(expand_lab: Lab, step: str) -> None:
    lab = expand_lab
    previous_on_0004(lab, step)
    session = rep_session(lab)
    seeded = created(lab, session, SEEDED)
    by_id_before = read(lab, session, seeded["id"])
    list_before = listed(lab, session)
    rows_before = lab.sql(OLD_ROWS)
    assert len(rows_before) == 2

    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.versions() == [HEAD]
    assert lab.sql(OLD_ROWS) == rows_before
    assert lab.sql(NEW_COLUMNS) == [[""] * 7]
    assert lab.sql("SELECT count(*) FROM customer WHERE nip IS NULL AND street IS NULL") == [["1"]]

    head_backend(lab)
    by_id_after = read(lab, session, seeded["id"]).json()
    assert without_new_fields(by_id_after) == by_id_before.json()
    # The list is unchanged in shape and content (Out of scope: new fields in the list).
    assert listed(lab, session).content == list_before.content


def test_k06_previous_backend_on_expanded_schema(expand_lab: Lab, step: str) -> None:
    lab = expand_lab
    previous_on_0004(lab, step)
    session = rep_session(lab)
    seeded = created(lab, session, SEEDED)
    by_id_before = read(lab, session, seeded["id"]).content
    list_before = listed(lab, session).json()

    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.versions() == [HEAD]
    assert lab.composition.inspect("backend")["Config"]["Image"] == step

    # The previous backend, unaware of the new columns, reads and creates on them.
    assert read(lab, session, seeded["id"]).content == by_id_before
    second = created(lab, session, {**SEEDED, "name": "Gospodarstwo Druga Wersja"})
    assert set(second) == {"id", "name", "country", "contacts"}
    assert read(lab, session, second["id"]).json() == second
    assert {item["id"] for item in listed(lab, session).json()["items"]} == {
        *(item["id"] for item in list_before["items"]),
        second["id"],
    }
    assert lab.sql(NEW_COLUMNS) == [[""] * 7, [""] * 7]

    # Contrast: the head backend returns the new fields for a customer created after the step.
    head_backend(lab)
    addressed = created(lab, session, ADDRESSED)
    assert {k: addressed[k] for k in ADDRESSED if k != "name"} == {
        k: v for k, v in ADDRESSED.items() if k != "name"
    }
    assert without_new_fields(read(lab, session, second["id"]).json())["name"] == (
        "Gospodarstwo Druga Wersja"
    )


def test_k06_c26_blocked_expand_previous_backend_answers(expand_lab: Lab, step: str) -> None:
    lab = expand_lab
    previous_on_0004(lab, step)
    session = rep_session(lab)
    seeded = created(lab, session, SEEDED)
    by_id_before = read(lab, session, seeded["id"]).content
    list_before = listed(lab, session).content
    before = lab.comparison_dump()

    holder = PsqlSession(lab.composition, role="eko_app", name="eko-test-eko302-holder")
    holder.query("BEGIN")
    holder.query("SELECT count(*) FROM customer")
    run = lab.start_migrate()
    try:
        granted_at = lab.wait_until("advisory lock granted", lambda: granted(lab, run))
        lab.wait_until("migrate waits for the table", lambda: waits_for_a_table_lock(lab, run), 4)
        asked = time.monotonic()
        by_id_during = read(lab, session, seeded["id"]).content
        list_during = listed(lab, session).content
        answered = time.monotonic()
        code = run.wait(30)
        logs = run.logs()
        exited_at = run.exited_at[0]
    finally:
        holder.close()
        run.remove()
    assert code != 0, logs
    assert '"cause":"psycopg.errors.LockNotAvailable"' in logs, logs[-2000:]
    assert LOCK_TIMEOUT - TOLERANCE <= exited_at - granted_at < LOCK_TIMEOUT + MARGIN
    assert (by_id_during, list_during) == (by_id_before, list_before)
    assert answered - asked < LOCK_TIMEOUT + MARGIN
    assert lab.comparison_dump() == before
    again = time.monotonic()
    assert read(lab, session, seeded["id"]).content == by_id_before
    assert time.monotonic() - again < AT_ONCE

    # Contrast: with the lock released the same migrate succeeds, and the head backend returns
    # the new fields for a customer created after it.
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.comparison_dump() != before
    head_backend(lab)
    addressed = created(lab, session, ADDRESSED)
    assert json.loads(read(lab, session, addressed["id"]).content)["county"] == "Warszawa"
