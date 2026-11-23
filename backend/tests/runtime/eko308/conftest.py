"""EKO-3-08 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, and the readers of the
staff display-name copy, the reps list and the retention run. Every value is synthetic (ADR-0005):
staff names are invented, subjects are fixed test UUIDs.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.runtime.eko201.conftest import Browser, FakeClock
from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko301.conftest import Crm
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers

COPY_TABLE = "staff_display_name"
COPY_COLUMNS = ("subject", "display_name", "is_rep", "last_login_at")
SESSION = "/api/auth/session"
REPS = "/api/reps"
CORRELATION = "eko-correlation-id"

R1 = "5a1e0308-0000-4000-8000-0000000000a1"
R2 = "5a1e0308-0000-4000-8000-0000000000a2"
M1 = "5a1e0308-0000-4000-8000-0000000000b1"
M2 = "5a1e0308-0000-4000-8000-0000000000b2"
A1 = "5a1e0308-0000-4000-8000-0000000000c1"
Z = "5a1e0308-0000-4000-8000-0000000000d1"


@dataclass(frozen=True)
class Copy:
    display_name: str | None
    is_rep: bool
    last_login_at: datetime


def copy_table_exists(pg: Postgres) -> bool:
    return pg.rows("SELECT to_regclass(%s)", (COPY_TABLE,)) != [(None,)]


def copies(pg: Postgres) -> dict[str, Copy]:
    """Every stored copy by subject; none before the table exists, so a test fails on its own
    terms there instead of on a missing table."""
    if not copy_table_exists(pg):
        return {}
    rows = pg.rows("SELECT subject, display_name, is_rep, last_login_at FROM staff_display_name")
    return {subject: Copy(name, rep, at) for subject, name, rep, at in rows}


def raw_copy_rows(pg: Postgres) -> list[tuple[Any, ...]]:
    """Every column of every copy, as text: what "byte-equal" and "no marker" compare."""
    if not copy_table_exists(pg):
        return []
    return pg.rows(
        'SELECT to_jsonb(c)::text FROM staff_display_name c ORDER BY subject COLLATE "C"'
    )


@pytest.fixture
def clean_copies(pg: Postgres) -> Iterator[None]:
    if copy_table_exists(pg):
        with pg.connect() as connection:
            connection.execute("TRUNCATE staff_display_name")
    yield


@dataclass
class Staff:
    """`Crm` with the token's display name and extra claims chosen per login."""

    crm: Crm
    clock: FakeClock

    @property
    def stub(self) -> oidc_stub.Stub:
        return self.crm.stub

    @property
    def pg(self) -> Postgres:
        return self.crm.pg

    @property
    def app(self) -> FastAPI:
        return self.crm.app

    def login(
        self,
        subject: str,
        roles: list[Any],
        name: str | None = "Synthetic Rep",
        **claims: Any,
    ) -> Browser:
        """A real login whose access token carries `name` (`None`: no `name` claim at all)."""
        self.stub.access_overrides = {"name": name, **claims}
        return self.crm.login(subject, roles)


@pytest.fixture
def staff(
    make_app: Any,
    browser_for: Any,
    stub: oidc_stub.Stub,
    pg: Postgres,
    clock: FakeClock,
    clean_customers: None,
    clean_copies: None,
) -> Staff:
    return Staff(Crm(make_app(), pg, stub, browser_for), clock)


def answer(response: httpx.Response) -> tuple[int, bytes, list[tuple[str, str]]]:
    """Status, body and headers but `Eko-Correlation-Id`: "byte-equal" (ADR-0003-C33)."""
    headers = sorted((k.lower(), v) for k, v in response.headers.multi_items())
    return response.status_code, response.content, [h for h in headers if h[0] != CORRELATION]


def rep_entries(browser: Browser) -> list[dict[str, Any]]:
    response = browser.send("GET", REPS)
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    # The list and nothing else: no count, no paging field (K-02).
    assert set(body) == {"items"}, body
    entries: list[dict[str, Any]] = body["items"]
    return entries


def rep_subjects(browser: Browser) -> set[str]:
    return {entry["subject"] for entry in rep_entries(browser)}


def session_view(browser: Browser) -> dict[str, Any]:
    response = browser.send("GET", SESSION)
    assert response.status_code == 200, response.text[:300]
    view: dict[str, Any] = response.json()
    return view


def run_retention(pg: Postgres, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> float:
    """One run of the worker's retention, `retention.run_once`, at the test's clock."""
    from app.core.settings import Settings, load_settings
    from app.data.database import Database
    from app.services.retention import run_once

    with monkeypatch.context() as scoped:
        for name, value in pg.app_env().items():
            scoped.setenv(name, value)
        database = Database.from_settings(load_settings(Settings))
    try:
        return run_once(database, clock)
    finally:
        database.dispose()
