"""EKO-3-03 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, and what the duplicate
NIP criteria compare: the fixed refusal, the headers that may differ, and the stored rows read
outside the API. Every value is synthetic (ADR-0005); every NIP is built at run time (G-7 A of
EKO-3-02), never written as a literal.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql
from sqlalchemy import Connection, Engine, event
from sqlalchemy.exc import OperationalError

from tests.runtime.eko201.conftest import Browser
from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko301.conftest import REP_A, Crm, create
from tests.support.pg_instance import BACKEND, MIGRATE_ENV, SUPERUSER_PASSWORD, Postgres

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers
crm = eko301.crm

# A rep with no customers at all (K-02 edge), apart from EKO-3-01's subjects.
REP_C = "5a1e0303-0000-4000-8000-00000000000c"
NIP_TAKEN_TEXT = "a customer with this NIP already exists - contact your manager"
NIP_TAKEN = {"detail": NIP_TAKEN_TEXT}
NIP_TAKEN_BODY = b'{"detail":"a customer with this NIP already exists - contact your manager"}'
NOT_PERMITTED = {"detail": "not permitted"}
CORRELATION = "eko-correlation-id"
UUID_FORM = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")

ROW = (
    "SELECT id, name, country, owner_subject, street, postal_code, town, voivodeship, county, "
    "nip, foreign_tax_id FROM customer WHERE id = %s"
)
CONTACT_ROWS = (
    "SELECT id, position, kind, value, note, is_primary FROM customer_contact "
    "WHERE customer_id = %s ORDER BY position"
)


def headers_but(response: httpx.Response, *names: str) -> list[tuple[str, str]]:
    """Every header as sent, in order, without the named ones (compared lower-case)."""
    left_out = {CORRELATION, *(name.lower() for name in names)}
    return [(k.lower(), v) for k, v in response.headers.multi_items() if k.lower() not in left_out]


def same_answer(first: httpx.Response, second: httpx.Response) -> bool:
    """Equal in status, body bytes and every header but `Eko-Correlation-Id`."""
    return (
        first.status_code == second.status_code
        and first.content == second.content
        and headers_but(first) == headers_but(second)
    )


def stored_customer(crm: Crm, customer_id: str) -> tuple[list[tuple[Any, ...]], ...]:
    """The customer's row and its contact rows as PostgreSQL holds them."""
    return crm.pg.rows(ROW, (customer_id,)), crm.pg.rows(CONTACT_ROWS, (customer_id,))


def holders(crm: Crm, nip: str) -> list[tuple[Any, ...]]:
    """`(id, owner_subject)` of every customer stored with `nip`."""
    return crm.pg.rows("SELECT id, owner_subject FROM customer WHERE nip = %s", (nip,))


def body(name: str, tax_id: str | None = None, **fields: Any) -> dict[str, Any]:
    found: dict[str, Any] = {"name": name, **fields}
    if tax_id is not None:
        found["tax_id"] = tax_id
    return found


def full_body(name: str, tax_id: str, marker: str = "K01") -> dict[str, Any]:
    """A create with an address and two contacts, so "stores nothing" covers every table."""
    return {
        "name": name,
        "street": f"ul. Znacznikowa {marker}",
        "postal_code": "00-950",
        "town": "Warszawa",
        "tax_id": tax_id,
        "contacts": [
            {"kind": "phone", "value": "+48601303303", "note": f"Pan {marker}", "primary": True},
            {"kind": "email", "value": f"{marker.lower()}@farm.example.invalid"},
        ],
    }


CUSTOMER_INSERT = "INSERT INTO customer "
INSERTED = "eko303_customer_insert"
WAITING_ON_A_TRANSACTION = (
    "SELECT count(*) FROM pg_locks WHERE locktype = 'transactionid' AND NOT granted"
)
# Ends the application's sessions a failed overlap leaves waiting, so the test fails, not hangs.
END_WAITING = (
    "SELECT pg_terminate_backend(l.pid) FROM pg_locks l "
    "WHERE l.locktype = 'transactionid' AND NOT l.granted"
)


class CommitGate:
    """Holds the commit of the first transaction that inserted a customer once armed, with its
    rows written and uncommitted, until the test releases it; optionally fails that commit, so
    the transaction rolls back. Test instrumentation on the application's own engine."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.armed = False
        self.fail = False
        self.inserted = threading.Event()
        self.released = threading.Event()
        event.listen(engine, "before_cursor_execute", self._seen)
        event.listen(engine, "commit", self._commit)
        event.listen(engine, "rollback", self._rolled_back)

    def _seen(self, conn: Connection, cursor: Any, statement: str, *rest: Any) -> None:
        if statement.startswith(CUSTOMER_INSERT):
            conn.info[INSERTED] = True

    def _rolled_back(self, conn: Connection) -> None:
        conn.info.pop(INSERTED, None)

    def _commit(self, conn: Connection) -> None:
        if not conn.info.pop(INSERTED, False) or not self.armed:
            return
        self.armed = False
        self.inserted.set()
        if not self.released.wait(60):
            raise AssertionError("the held commit was never released")
        if self.fail:
            # Raising here skips the driver's commit, and the pool would then return the
            # connection without a rollback, still holding the row locks: roll back first.
            conn.connection.dbapi_connection.rollback()  # type: ignore[union-attr]  # checked out
            raise OperationalError("a forced failure after the insert", None, Exception())

    def remove(self) -> None:
        event.remove(self.engine, "before_cursor_execute", self._seen)
        event.remove(self.engine, "commit", self._commit)
        event.remove(self.engine, "rollback", self._rolled_back)


@pytest.fixture
def gate(crm: Crm) -> Iterator[CommitGate]:
    held = CommitGate(crm.app.state.database.engine)
    try:
        yield held
    finally:
        held.released.set()
        held.remove()


def waiting_inserts(crm: Crm) -> int:
    [(count,)] = crm.pg.rows(WAITING_ON_A_TRANSACTION)
    return int(count)


@dataclass
class Overlap:
    winner: httpx.Response
    loser: httpx.Response
    loser_waited: bool


def overlapped(
    crm: Crm,
    gate: CommitGate,
    first: tuple[Browser, dict[str, Any]],
    second: tuple[Browser, dict[str, Any]],
) -> Overlap:
    """`first`'s create reaches its commit and is held there; `second`'s create is sent while it
    is held. When the second insert waits on the first transaction (a lock wait in `pg_locks`),
    the first is released; otherwise the second is let finish before the release."""
    gate.armed = True
    futures: list[Future[httpx.Response]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            winner = pool.submit(create, *first)
            futures.append(winner)
            if not gate.inserted.wait(30):
                raise AssertionError("the first create never reached its commit")
            loser = pool.submit(create, *second)
            futures.append(loser)
            deadline = time.monotonic() + 20
            waited = False
            while time.monotonic() < deadline and not loser.done():
                if waiting_inserts(crm) == 1:
                    waited = True
                    break
                time.sleep(0.05)
            if not waited:
                loser.result(timeout=20)
            gate.released.set()
            return Overlap(winner.result(timeout=60), loser.result(timeout=60), waited)
        finally:
            gate.released.set()
            if not all(future.done() for future in futures):
                crm.pg.rows(END_WAITING)


def second_browser(crm: Crm, first: Browser) -> Browser:
    """Another client holding the same session, so one rep can have two requests in flight."""
    other = crm.open_browser(crm.app)
    other.jar.update(first.jar)
    return other


# Revision 0007 (K-05): databases of their own on the test's server, migrated by `migrate` as it
# runs (`alembic upgrade head`), from this tree or from this tree as of revision 0006.
REVISION = "0007"
PREVIOUS = "0006"
REFUSAL = re.compile(
    r"migrate refused: revision 0007 needs every NIP unique; "
    r"NIP values held by more than one customer: (?P<count>[0-9]+)"
)
PLANT = (
    "INSERT INTO customer (id, name, country, owner_subject, nip, foreign_tax_id) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
ROWS = (
    "SELECT id, name, country, owner_subject, street, postal_code, town, voivodeship, county, "
    "nip, foreign_tax_id FROM customer ORDER BY id"
)
NIP_CONSTRAINT = (
    "SELECT c.contype, pg_get_constraintdef(c.oid), i.indnullsnotdistinct FROM pg_constraint c "
    "JOIN pg_index i ON i.indexrelid = c.conindid "
    "WHERE c.conrelid = 'customer'::regclass AND c.conname = 'uq_customer_nip'"
)


def previous_tree(directory: Path) -> Path:
    """This backend as of revision 0006: the same files with revision 0007's and every later
    one's left out, so its `migrate` brings a database to 0006 exactly as the code before this
    task did."""
    target = directory / "backend-0006"
    if target.exists():
        return target
    skipped = shutil.ignore_patterns("__pycache__", f"{REVISION}_*", "000[89]_*", "00[1-9][0-9]_*")
    shutil.copytree(BACKEND / "app", target / "app", ignore=skipped)
    shutil.copytree(BACKEND / "migrations", target / "migrations", ignore=skipped)
    shutil.copy2(BACKEND / "alembic.ini", target / "alembic.ini")
    return target


def tree_as_of_0007(directory: Path) -> Path:
    """This backend as of revision 0007: the same files with every revision after 0007 left out,
    so its `migrate` brings a database to 0007 and no further (X-5 A of EKO-3-05)."""
    target = directory / "backend-0007"
    if target.exists():
        return target
    skipped = shutil.ignore_patterns("__pycache__", "000[89]_*", "00[1-9][0-9]_*")
    shutil.copytree(BACKEND / "app", target / "app", ignore=skipped)
    shutil.copytree(BACKEND / "migrations", target / "migrations", ignore=skipped)
    shutil.copy2(BACKEND / "alembic.ini", target / "alembic.ini")
    return target


def new_database(pg: Postgres, name: str) -> None:
    with pg.connect() as connection:
        dropped = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
        connection.execute(dropped.format(sql.Identifier(name)))
        connection.execute(
            sql.SQL(
                "CREATE DATABASE {} OWNER eko_app TEMPLATE template0 ENCODING 'UTF8' "
                "LOCALE_PROVIDER icu ICU_LOCALE 'pl-PL' LOCALE 'C.UTF-8'"
            ).format(sql.Identifier(name))
        )


def connect_to(pg: Postgres, database: str) -> psycopg.Connection[Any]:
    return psycopg.connect(
        host="127.0.0.1", port=pg.port, dbname=database, user="postgres",
        password=SUPERUSER_PASSWORD, autocommit=True,
    )  # fmt: skip


def rows_of(pg: Postgres, database: str, query: str, params: Any = ()) -> list[tuple[Any, ...]]:
    with connect_to(pg, database) as connection:
        return list(connection.execute(query, params).fetchall())


def migrate_command(pg: Postgres, database: str, backend: Path = BACKEND) -> dict[str, Any]:
    env = {**os.environ, **pg.app_env(1, 0), "APP_DB_NAME": database, **MIGRATE_ENV}
    return {
        "args": [sys.executable, "-m", "alembic", "upgrade", "head"],
        "cwd": backend,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
    }


def run_migrate(pg: Postgres, database: str, backend: Path = BACKEND) -> tuple[int, str]:
    """`migrate`'s exit code and its whole output, standard error included."""
    done = subprocess.run(**migrate_command(pg, database, backend), timeout=180, check=False)
    return done.returncode, done.stdout


def versions(pg: Postgres, database: str) -> list[str]:
    return [row[0] for row in rows_of(pg, database, "SELECT version_num FROM alembic_version")]


def at_previous(pg: Postgres, database: str, directory: Path) -> None:
    """A new database brought to revision 0006 by the code as of 0006."""
    new_database(pg, database)
    code, output = run_migrate(pg, database, previous_tree(directory))
    assert code == 0, output[-2000:]
    assert versions(pg, database) == [PREVIOUS]


def plant(pg: Postgres, database: str, *rows: tuple[str, str | None, str | None]) -> None:
    """Customers written straight through SQL, as a writer past the services would: each row is
    `(country, nip, foreign_tax_id)`."""
    with connect_to(pg, database) as connection:
        for index, (country, nip, foreign) in enumerate(rows):
            connection.execute(
                PLANT, (uuid.uuid4(), f"Gospodarstwo K05 {index}", country, REP_A, nip, foreign)
            )


def refused_count(output: str) -> int | None:
    found = [REFUSAL.fullmatch(line.strip()) for line in output.splitlines()]
    matches = [match for match in found if match is not None]
    if len(matches) != 1:
        return None
    return int(matches[0]["count"])
