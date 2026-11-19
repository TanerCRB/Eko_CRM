"""EKO-3-01 carriers: the shipped `create_app()` on real PostgreSQL 18 and the local OIDC stub.

EKO-2-01's carrier fixtures are bound here by name (they live in a sibling directory's conftest).
`Crm` logs a synthetic staff member in with a chosen subject and client roles, so two reps, a
manager and the refused callers each hold their own real session. Every value is synthetic
(ADR-0005, "Synthetic customer data until the impact assessment").
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from psycopg import sql

from tests.runtime.eko201 import conftest as eko201
from tests.runtime.eko201.conftest import AppFactory, Browser
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pg = eko201.pg
clean = eko201.clean
stub = eko201.stub
clock = eko201.clock
make_app = eko201.make_app
browser_for = eko201.browser_for

CUSTOMERS = "/api/customers"
REP_A = "5a1e0301-0000-4000-8000-00000000000a"
REP_B = "5a1e0301-0000-4000-8000-00000000000b"
MANAGER = "5a1e0301-0000-4000-8000-0000000000aa"
REP_AND_MANAGER = "5a1e0301-0000-4000-8000-0000000000ab"
ADMINISTRATOR = "5a1e0301-0000-4000-8000-0000000000ad"
ROLE_LESS = "5a1e0301-0000-4000-8000-0000000000ff"
OWNED_TABLES = ("customer_contact", "customer")


def customer_url(customer_id: str) -> str:
    return f"{CUSTOMERS}/{customer_id}"


@pytest.fixture
def clean_customers(pg: Postgres) -> None:
    with pg.connect() as connection:
        for table in OWNED_TABLES:
            # Before revision 0004 exists the tables do not, and the test fails on its own terms.
            if connection.execute("SELECT to_regclass(%s)", (table,)).fetchone() != (None,):
                connection.execute(sql.SQL("TRUNCATE {} CASCADE").format(sql.Identifier(table)))


def stored_counts(pg: Postgres) -> dict[str, int]:
    counts = {}
    with pg.connect() as connection:
        for table in OWNED_TABLES:
            if connection.execute("SELECT to_regclass(%s)", (table,)).fetchone() == (None,):
                counts[table] = 0
                continue
            count = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            row = connection.execute(count).fetchone()
            assert row is not None
            counts[table] = row[0]
    return counts


@dataclass
class Crm:
    """The application under test and a way to hold a real session as a given staff member."""

    app: FastAPI
    pg: Postgres
    stub: oidc_stub.Stub
    open_browser: Callable[[FastAPI], Browser]

    def login(self, subject: str, roles: list[Any]) -> Browser:
        self.stub.next_user = oidc_stub.User(sub=subject, client_roles=roles)
        browser = self.open_browser(self.app)
        browser.login()
        assert browser.session is not None, "the synthetic login made no session"
        return browser

    def counts(self) -> dict[str, int]:
        return stored_counts(self.pg)


@pytest.fixture
def crm(
    make_app: AppFactory,
    browser_for: Callable[[FastAPI], Browser],
    stub: oidc_stub.Stub,
    pg: Postgres,
    clean_customers: None,
) -> Crm:
    return Crm(make_app(), pg, stub, browser_for)


def create(browser: Browser, body: Any) -> httpx.Response:
    return browser.send("POST", CUSTOMERS, json=body)


def created_id(browser: Browser, body: Any) -> str:
    response = create(browser, body)
    assert response.status_code == 201, response.text
    identifier: str = response.json()["id"]
    return identifier


def listed_ids(browser: Browser) -> set[str]:
    response = browser.send("GET", CUSTOMERS)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}
