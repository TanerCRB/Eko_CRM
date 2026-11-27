"""EKO-4-01 K-07 (Issue "What must stay as it is"; ADR-0005 PD-C2 and *What may appear in logs*;
ACC-8; Out of scope EKO-5): planning or reading a visit writes nothing but the visit, makes no
outbound call, and puts no customer or visit value in a log.

One scenario runs every operation of the task: a successful plan with an own address, each K-01 and
K-03 refusal, the day, week and all-visits lists and the by-id read. Around it: every customer and
contact row, every other application table, an outbound-connection recorder in this process (which
the application's HTTP client and the test's login both go through), and every in-process logger at
DEBUG. Runtime, on real PostgreSQL and the OIDC stub; every value is synthetic.
"""

import socket
import unicodedata
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql

from tests.runtime.eko201.conftest import Browser
from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, Crm
from tests.runtime.eko303.test_eko303_k06_no_nip_in_any_log import every_logger_at_debug
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import (
    backend_records,
    logged_text,
)
from tests.runtime.eko305.conftest import archive, edit, snapshot
from tests.runtime.eko401.conftest import (
    all_visits,
    customer,
    period,
    plan,
    planned,
    read_visit,
    visit_body,
    visit_rows,
)
from tests.support import log_lines as ll
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

TOKEN = "k07e401"
ADDRESS_MARKER = f"Zagrodowa-{TOKEN}-ąę"
NAME_MARKER = f"Łąka-{TOKEN}"
PHONE_MARKER = "+48601040107"
EMAIL_MARKER = f"{TOKEN}@visit.example"
MARKERS = tuple(
    form
    for marker in (ADDRESS_MARKER, NAME_MARKER, PHONE_MARKER, EMAIL_MARKER)
    for form in {unicodedata.normalize("NFC", marker), unicodedata.normalize("NFD", marker)}
)
DAY = "2026-11-30"


def application_tables(pg: Postgres) -> list[str]:
    return [
        name
        for (name,) in pg.rows(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
    ]


def every_row_but_visits(pg: Postgres) -> dict[str, list[str]]:
    """Every row of every application table but the visit table, each as its text."""
    rows = {}
    with pg.connect() as connection:
        for table in application_tables(pg):
            if table == "visit":
                continue
            query = sql.SQL("SELECT to_jsonb(t)::text FROM {} t ORDER BY 1").format(
                sql.Identifier(table)
            )
            rows[table] = [row[0] for row in connection.execute(query).fetchall()]
    return rows


class Outbound:
    """Every connection a Python socket of this process opens, by address: the application's
    HTTP client and the test's own requests to the OIDC stub alike. The database driver's own C
    library connects past it; PostgreSQL is no outbound host."""

    def __init__(self) -> None:
        self.addresses: list[Any] = []

    def __call__(self, real: Any) -> Any:
        def recorded(sock: socket.socket, address: Any, *rest: Any) -> Any:
            self.addresses.append(address)
            return real(sock, address, *rest)

        return recorded


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> Iterator[Outbound]:
    recorder = Outbound()
    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, recorder(getattr(socket.socket, name)))
    yield recorder


class Scene:
    """Rep A with a customer carrying every marker, rep B with its own customer, the manager and
    a `rep`+`manager` caller; every session made before anything is measured."""

    def __init__(self, crm: Crm) -> None:
        self.rep_a, self.rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
        self.manager = crm.login(MANAGER, ["manager"])
        self.both = crm.login(REP_AND_MANAGER, ["rep", "manager"])
        self.marked = customer(
            self.rep_a,
            NAME_MARKER,
            street="ul. Polna 1",
            contacts=[
                {"kind": "phone", "value": PHONE_MARKER, "primary": True},
                {"kind": "email", "value": EMAIL_MARKER},
            ],
        )
        self.archived = customer(self.rep_a, "Gospodarstwo Archiwalne")
        assert archive(self.rep_a, self.archived).status_code == 200
        self.of_b = customer(self.rep_b, "Gospodarstwo B")


def every_operation(scene: Scene) -> list[Any]:
    """The task's every operation once, refusals included; the answers in order."""
    a, marked = scene.rep_a, scene.marked
    created = planned(a, visit_body(marked, own_address=ADDRESS_MARKER))
    answers: list[Any] = [
        created,
        plan(a, visit_body(marked)),
        plan(a, visit_body(scene.of_b, own_address=ADDRESS_MARKER)),
        plan(a, visit_body(str(uuid.uuid4()), own_address=ADDRESS_MARKER)),
        plan(a, visit_body(scene.archived, own_address=ADDRESS_MARKER)),
        plan(scene.manager, visit_body(marked, own_address=ADDRESS_MARKER)),
        plan(scene.both, visit_body(marked, own_address=ADDRESS_MARKER)),
        plan(
            a,
            visit_body(
                marked, ("2026-10-25", "02:30"), ("2026-10-25", "04:00"), own_address=ADDRESS_MARKER
            ),
        ),  # fmt: skip
        plan(
            a,
            visit_body(
                marked, ("2026-03-29", "02:30"), ("2026-03-29", "04:00"), own_address=ADDRESS_MARKER
            ),
        ),  # fmt: skip
        plan(a, visit_body(marked, (DAY, "11:00"), (DAY, "10:00"), own_address=ADDRESS_MARKER)),
        plan(a, visit_body(marked, own_address=ADDRESS_MARKER + "x" * 300)),
        plan(a, visit_body(marked, own_address=ADDRESS_MARKER, owner_subject=REP_B)),
        period(a, DAY),
        period(a, DAY, "2026-12-06"),
        all_visits(a),
        read_visit(a, created["id"]),
    ]
    return answers


def test_k07_planning_and_reading_change_no_customer_and_no_other_table(crm: Crm) -> None:
    scene = Scene(crm)
    customers_before, others_before = snapshot(crm), every_row_but_visits(crm.pg)
    assert "customer" in others_before and "app_session" in others_before
    every_operation(scene)
    assert snapshot(crm) == customers_before
    assert every_row_but_visits(crm.pg) == others_before
    assert len(visit_rows(crm.pg)) == 2


def test_k07_contrast_editing_the_customer_does_change_its_row(crm: Crm) -> None:
    scene = Scene(crm)
    before = snapshot(crm)
    changed = edit(scene.rep_a, scene.marked, {"name": NAME_MARKER, "street": ADDRESS_MARKER})
    assert changed.status_code == 200, changed.text
    assert snapshot(crm) != before


def test_k07_no_outbound_connection_is_opened_by_a_visit_operation(
    crm: Crm, outbound: Outbound
) -> None:
    scene = Scene(crm)
    # Contrast: the login itself is recorded, so the recorder sees a connection when one is made.
    assert outbound.addresses, "the recorder saw no login connection: it would see nothing"
    outbound.addresses.clear()
    every_operation(scene)
    assert outbound.addresses == []


def test_k07_no_customer_or_visit_value_reaches_a_log_line(
    crm: Crm, caplog: pytest.LogCaptureFixture
) -> None:
    scene = Scene(crm)
    every_logger_at_debug(caplog)
    answers = every_operation(scene)
    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    assert ll.leaks(logged_text(caplog.records), *MARKERS) == []
    # Contrast: the marker is in the create answer itself, so the capture would see a leak.
    assert ADDRESS_MARKER in str(answers[0])


def texts(responses: list[Any]) -> str:
    return "\n".join(r.text for r in responses)


def test_k07_rep_b_answers_carry_no_marker_of_rep_as_customers_or_visits(crm: Crm) -> None:
    scene = Scene(crm)
    visit_id = every_operation(scene)[0]["id"]
    b: Browser = scene.rep_b
    answers = [
        period(b, DAY),
        period(b, DAY, "2026-12-06"),
        all_visits(b),
        read_visit(b, visit_id),
        plan(b, visit_body(scene.marked)),
    ]
    assert [r.status_code for r in answers] == [200, 200, 200, 404, 404]
    assert [m for m in MARKERS if m in texts(answers)] == []
    assert visit_id not in texts(answers)


def test_k07_edge_without_an_own_address_the_visit_shows_the_customers_current_address(
    crm: Crm,
) -> None:
    scene = Scene(crm)
    bare = planned(scene.rep_a, visit_body(scene.marked))
    own = planned(scene.rep_a, visit_body(scene.marked, own_address="Pole za lasem"))
    assert (bare["own_address"], bare["customer"]["street"]) == (None, "ul. Polna 1")
    changed = edit(scene.rep_a, scene.marked, {"name": NAME_MARKER, "street": "ul. Nowa 2"})
    assert changed.status_code == 200, changed.text
    bare_now = read_visit(scene.rep_a, bare["id"]).json()
    own_now = read_visit(scene.rep_a, own["id"]).json()
    assert (bare_now["own_address"], bare_now["customer"]["street"]) == (None, "ul. Nowa 2")
    assert own_now["own_address"] == "Pole za lasem"


def test_k07_edge_a_repeated_create_makes_a_second_visit(crm: Crm) -> None:
    scene = Scene(crm)
    body = visit_body(scene.marked)
    first, second = planned(scene.rep_a, body), planned(scene.rep_a, body)
    assert first["id"] != second["id"]
    assert len(visit_rows(crm.pg)) == 2
