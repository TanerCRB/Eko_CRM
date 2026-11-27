"""EKO-4-01 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, with the application's
clock set to the test's frozen one (ADR-0002-C13), and the readers of the stored visit rows. A
visit whose customer another subject owns is planted through SQL, since reassignment does not
exist yet (K-02). Every value is synthetic (ADR-0005).
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.runtime.eko201.conftest import AppFactory, Browser, FakeClock
from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko301.conftest import Crm, created_id
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers

VISITS = "/api/visits"
PERIOD = "/api/visits/period"
CORRELATION = "eko-correlation-id"
NOT_FOUND = (404, {"detail": "not found"})
NOT_PERMITTED = (403, {"detail": "not permitted"})
RESTORE_FIRST = (409, {"detail": "restore it first"})
EMPTY: dict[str, list[Any]] = {"items": []}
# Every column of the visit table as PostgreSQL holds it.
VISIT_COLUMNS = ("id", "customer_id", "owner_subject", "starts_at", "ends_at", "own_address")
VISIT_ROWS = (
    "SELECT id::text, customer_id::text, owner_subject, starts_at, ends_at, own_address "
    "FROM visit ORDER BY id"
)
# A customer no login holds: the owner of planted customers in the K-02 scenario.
ELSEWHERE = "5a1e0401-0000-4000-8000-0000000000e1"


@pytest.fixture
def crm(
    make_app: AppFactory,
    browser_for: Callable[[FastAPI], Browser],
    stub: oidc_stub.Stub,
    pg: Postgres,
    clock: FakeClock,
    clean_customers: None,
) -> Crm:
    """EKO-3-01's carrier, with the application's clock the test's (ADR-0002-C13). Truncating
    the customer table with CASCADE empties the visit table too."""
    app = make_app()
    app.state.clock = clock
    return Crm(app, pg, stub, browser_for)


def answer(response: httpx.Response) -> tuple[int, bytes, list[tuple[str, str]]]:
    """Status, body and headers but `Eko-Correlation-Id`: "byte-equal" (ADR-0003-C33)."""
    headers = sorted((k.lower(), v) for k, v in response.headers.multi_items())
    return response.status_code, response.content, [h for h in headers if h[0] != CORRELATION]


def status_and_json(response: httpx.Response) -> tuple[int, Any]:
    return response.status_code, response.json()


def wall(day: str, at: str) -> dict[str, str]:
    return {"date": day, "time": at}


def visit_body(
    customer_id: str,
    start: tuple[str, str] = ("2026-11-30", "10:00"),
    end: tuple[str, str] = ("2026-11-30", "11:00"),
    **fields: Any,
) -> dict[str, Any]:
    return {"customer_id": customer_id, "start": wall(*start), "end": wall(*end), **fields}


def plan(browser: Browser, body: Any) -> httpx.Response:
    return browser.send("POST", VISITS, json=body)


def planned(browser: Browser, body: Any) -> dict[str, Any]:
    response = plan(browser, body)
    assert response.status_code == 201, response.text[:500]
    created: dict[str, Any] = response.json()
    return created


def planned_id(browser: Browser, body: Any) -> str:
    identifier: str = planned(browser, body)["id"]
    return identifier


def visit_url(visit_id: str) -> str:
    return f"{VISITS}/{visit_id}"


def read_visit(browser: Browser, visit_id: str) -> httpx.Response:
    return browser.send("GET", visit_url(visit_id))


def period(browser: Browser, first: str, last: str | None = None) -> httpx.Response:
    return browser.send("GET", PERIOD, params={"first": first, "last": last or first})


def all_visits(browser: Browser) -> httpx.Response:
    return browser.send("GET", VISITS)


def items(response: httpx.Response) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.text[:500]
    found: list[dict[str, Any]] = response.json()["items"]
    return found


def ids(response: httpx.Response) -> list[str]:
    return [item["id"] for item in items(response)]


def customer(browser: Browser, name: str, **fields: Any) -> str:
    return created_id(browser, {"name": name, **fields})


def visit_rows(pg: Postgres) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in pg.rows(VISIT_ROWS)]


def visit_count(pg: Postgres) -> int:
    return int(pg.rows("SELECT count(*) FROM visit")[0][0])


def stored_visit(pg: Postgres, visit_id: str) -> dict[str, Any]:
    [row] = pg.rows(VISIT_ROWS.replace("ORDER BY id", "WHERE id = %s"), (visit_id,))
    return dict(zip(VISIT_COLUMNS, row, strict=True))


def raw_visit_row(pg: Postgres, visit_id: str) -> str:
    """Every column of the row as text: what "byte-equal" compares."""
    [(row,)] = pg.rows("SELECT to_jsonb(v)::text FROM visit v WHERE id = %s", (visit_id,))
    return str(row)


def plant_customer(pg: Postgres, owner: str, name: str, street: str | None = None) -> str:
    """A customer stored as revision 0004 holds one, with a UUIDv4 as the application issues."""
    customer_id = str(uuid.uuid4())
    pg.rows(
        "INSERT INTO customer (id, name, country, owner_subject, street) "
        "VALUES (%s, %s, 'PL', %s, %s) RETURNING id",
        (customer_id, name, owner, street),
    )
    return customer_id


def plant_visit(
    pg: Postgres,
    owner: str,
    customer_id: str,
    starts_at: datetime,
    ends_at: datetime,
    own_address: str | None = None,
) -> str:
    """A visit row written past the application: the K-02 case of a visit whose customer another
    subject owns, which no operation of this task can make."""
    visit_id = str(uuid.uuid4())
    pg.rows(
        "INSERT INTO visit (id, customer_id, owner_subject, starts_at, ends_at, own_address) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (visit_id, customer_id, owner, starts_at, ends_at, own_address),
    )
    return visit_id
