"""EKO-3-05 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, with the application's
clock set to the test's frozen one, and the readers of the stored rows the change operations must
leave alone. A seeded customer is stored by EKO-3-06's operator seed itself, run in-process on the
same server (D-8 Y-2 A). Every value is synthetic (ADR-0005); NIPs are built at run time (EKO-3-02
G-7 A).
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.domain.customers import ContactInput, CustomerInput
from app.seed_dataset import Record
from tests.runtime.eko201.conftest import AppFactory, Browser, FakeClock
from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko301.conftest import CUSTOMERS, Crm, created_id, customer_url
from tests.runtime.eko306 import conftest as eko306
from tests.runtime.eko306.conftest import SEED_B, SEED_C, Seeder
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers
seed = eko306.seed

CORRELATION = "eko-correlation-id"
EMPTY: dict[str, list[Any]] = {"items": []}
NOT_FOUND = (404, {"detail": "not found"})
NOT_PERMITTED = (403, {"detail": "not permitted"})
# Every column of the two owned tables, `dataset_key` and `archived_at` included (D-8 Y-2 A), read
# as PostgreSQL holds them; `archived_at` stays last.
CUSTOMER_COLUMNS = (
    "id",
    "name",
    "country",
    "owner_subject",
    "street",
    "postal_code",
    "town",
    "voivodeship",
    "county",
    "nip",
    "foreign_tax_id",
    "dataset_key",
    "archived_at",
)
CUSTOMER_ROWS = (
    "SELECT id::text, name, country, owner_subject, street, postal_code, town, voivodeship, "
    "county, nip, foreign_tax_id, dataset_key, archived_at FROM customer ORDER BY id"
)
CONTACT_ROWS = (
    "SELECT id::text, customer_id::text, position, kind, value, note, is_primary "
    "FROM customer_contact ORDER BY customer_id, position"
)


@pytest.fixture
def crm(
    make_app: AppFactory,
    browser_for: Callable[[FastAPI], Browser],
    stub: oidc_stub.Stub,
    pg: Postgres,
    clock: FakeClock,
    clean_customers: None,
) -> Crm:
    """EKO-3-01's carrier, with the application's clock the test's (ADR-0002-C13)."""
    app = make_app()
    app.state.clock = clock
    return Crm(app, pg, stub, browser_for)


def answer(response: httpx.Response) -> tuple[int, bytes, list[tuple[str, str]]]:
    """Status, body and headers but `Eko-Correlation-Id`: "byte-equal" (ADR-0003-C33)."""
    headers = sorted((k.lower(), v) for k, v in response.headers.multi_items())
    return response.status_code, response.content, [h for h in headers if h[0] != CORRELATION]


def status_and_json(response: httpx.Response) -> tuple[int, Any]:
    return response.status_code, response.json()


def customer(browser: Browser, name: str, **fields: Any) -> str:
    return created_id(browser, {"name": name, **fields})


def phone(value: str, note: str | None = None, primary: bool = False) -> dict[str, Any]:
    return {"kind": "phone", "value": value, "note": note, "primary": primary}


def email(value: str, note: str | None = None, primary: bool = False) -> dict[str, Any]:
    return {"kind": "email", "value": value, "note": note, "primary": primary}


def edit(browser: Browser, customer_id: str, body: Any) -> httpx.Response:
    return browser.send("PUT", customer_url(customer_id), json=body)


def archive(browser: Browser, customer_id: str) -> httpx.Response:
    return browser.send("POST", f"{customer_url(customer_id)}/archive")


def restore(browser: Browser, customer_id: str) -> httpx.Response:
    return browser.send("POST", f"{customer_url(customer_id)}/restore")


def read(browser: Browser, customer_id: str) -> httpx.Response:
    return browser.send("GET", customer_url(customer_id))


def read_json(browser: Browser, customer_id: str) -> dict[str, Any]:
    response = read(browser, customer_id)
    assert response.status_code == 200, response.text[:300]
    found: dict[str, Any] = response.json()
    return found


def search(browser: Browser, params: Any = None) -> httpx.Response:
    return browser.send("GET", CUSTOMERS, params=params)


def listed_items(browser: Browser, params: Any = None) -> list[dict[str, Any]]:
    response = search(browser, params)
    assert response.status_code == 200, response.text[:300]
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def found(browser: Browser, params: Any = None) -> set[str]:
    return {item["id"] for item in listed_items(browser, params)}


def customer_rows(crm: Crm) -> dict[str, tuple[Any, ...]]:
    """Every customer row by identifier, every column as PostgreSQL returns it."""
    return {row[0]: tuple(row) for row in crm.pg.rows(CUSTOMER_ROWS)}


def contact_rows(crm: Crm) -> dict[str, list[tuple[Any, ...]]]:
    """Every contact row, grouped by its customer, in stored order."""
    grouped: dict[str, list[tuple[Any, ...]]] = {}
    for row in crm.pg.rows(CONTACT_ROWS):
        grouped.setdefault(row[1], []).append(tuple(row))
    return grouped


def snapshot(crm: Crm) -> tuple[dict[str, tuple[Any, ...]], dict[str, list[tuple[Any, ...]]]]:
    return customer_rows(crm), contact_rows(crm)


def others(
    taken: tuple[dict[str, tuple[Any, ...]], dict[str, list[tuple[Any, ...]]]], target: str
) -> tuple[dict[str, tuple[Any, ...]], dict[str, list[tuple[Any, ...]]]]:
    """A snapshot without the target's own customer row and contacts."""
    rows, contacts = taken
    return (
        {k: v for k, v in rows.items() if k != target},
        {k: v for k, v in contacts.items() if k != target},
    )


def archived_at(crm: Crm, customer_id: str) -> Any:
    [(value,)] = crm.pg.rows("SELECT archived_at FROM customer WHERE id = %s", (customer_id,))
    return value


def stored_row(crm: Crm, customer_id: str) -> dict[str, Any]:
    """The customer's row by column name, `dataset_key` and `owner_subject` included."""
    return dict(zip(CUSTOMER_COLUMNS, customer_rows(crm)[customer_id], strict=True))


def as_input(body: dict[str, Any]) -> CustomerInput:
    """A request body as the seed's dataset states a record, before create's rules."""
    contacts = tuple(
        ContactInput(c["kind"], c["value"], c.get("note"), c.get("primary", False))
        for c in body.get("contacts", [])
    )
    return CustomerInput(
        **{**{k: v for k, v in body.items() if k != "contacts"}, "contacts": contacts}
    )


def seeded_customer(crm: Crm, seed: Seeder, owner: str, key: str, body: dict[str, Any]) -> str:
    """One customer stored by the operator seed under `owner` with dataset key `key`, as its load
    stores every record; the other two shares are empty."""
    run = seed((owner, SEED_B, SEED_C), [Record(key, 0, as_input(body))])
    assert (run.code, run.totals()["added"]) == (0, 1), run.lines
    [(customer_id,)] = crm.pg.rows("SELECT id::text FROM customer WHERE dataset_key = %s", (key,))
    return str(customer_id)
