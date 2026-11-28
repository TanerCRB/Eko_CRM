"""EKO-3-01 forwarded item F-2 A, ADR-0005-C17, on the shipped head (revision 0004): customers
are created after a backup set was taken; the database is restored from the set into an empty
server, customers are created there through the application's own store
(`app.data.customers.CustomerStore`), and none of their identifiers is one issued after the set.
The restored schema holds no sequence and no identifier default on the customer tables, so no
database state can hand an identifier out again.

F-1 A (product-table counts in the manifest) is in `test_adr0004_c15_backup_set_contents.py`.
This module stays separate because C17 needs the shipped head without the probe revision and a
restore server the application can reach on a local port, where the C15 restore runs on no
network. Every value is synthetic (ADR-0005).
"""

import secrets
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app.data.customers import CustomerStore
from app.data.database import Database
from app.domain.customers import Contact, ContactKind, CustomerDraft
from app.domain.ownership import OwnedBy
from tests.runtime.backup_lab import BackupLab, open_set, restore_psql, restore_set, set_names
from tests.runtime.lab import docker

pytestmark = pytest.mark.runtime

OWNER = "5a1e0301-0000-4000-8000-0000000000c7"
IMAGE = "postgres:18.6-trixie"


@contextmanager
def published_server() -> Iterator[tuple[str, int, str]]:
    """An empty server of the pinned image on a local port, so the application reaches it."""
    password = "synthetic-" + secrets.token_hex(12)
    container = docker(
        "run", "-d", "-p", "127.0.0.1::5432", "-e", f"POSTGRES_PASSWORD={password}", IMAGE,
    ).stdout.strip()  # fmt: skip
    try:
        deadline = time.monotonic() + 120
        while docker("exec", container, "pg_isready", "-h", "127.0.0.1", check=False).returncode:
            assert time.monotonic() < deadline, "the restore server did not start"
            time.sleep(1)
        # The server restarts once after its first initialisation; wait for the second start.
        time.sleep(2)
        while docker("exec", container, "pg_isready", "-h", "127.0.0.1", check=False).returncode:
            assert time.monotonic() < deadline, "the restore server did not start"
            time.sleep(1)
        mapped = docker("port", container, "5432/tcp").stdout.strip().splitlines()[0]
        yield container, int(mapped.rsplit(":", 1)[1]), password
    finally:
        docker("rm", "-f", container, check=False)


def store_on(port: int, password: str) -> tuple[CustomerStore, Database]:
    url = URL.create(
        "postgresql+psycopg",
        username="postgres",
        password=password,
        host="127.0.0.1",
        port=port,
        database="eko",
    )
    database = Database(create_engine(url, connect_args={"options": "-c timezone=UTC"}))
    return CustomerStore(database), database


def test_eko301_c17_no_identifier_issued_twice_after_a_restore(
    backup_lab: BackupLab,
) -> None:
    backup_lab.lab.at_head()
    [[revision]] = backup_lab.sql("SELECT version_num FROM alembic_version")
    assert revision == "0010"
    before = [backup_lab.plant_customer(OWNER, contacts=n) for n in (2, 0, 1)]
    names_before = set_names(backup_lab.double)
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - names_before
    contents = open_set(backup_lab.double, name, backup_lab.identity)
    after = {backup_lab.plant_customer(OWNER) for _ in range(5)}
    assert after.isdisjoint(before)
    with published_server() as (container, port, password):
        restore_set(container, contents)
        restored = {
            row[0]
            for row in restore_psql(container, "eko", "SELECT CAST(id AS text) FROM customer")
        }
        assert restored == set(before), "the restored set holds exactly the customers before it"
        [[contacts]] = restore_psql(container, "eko", "SELECT count(*) FROM customer_contact")
        assert int(contacts) == 3
        # F-2: nothing in the restored schema can issue an identifier.
        assert restore_psql(
            container,
            "eko",
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'S'",
        ) == [["app_session_id_seq"]], "only revision 0003's session identity has a sequence"
        assert (
            restore_psql(
                container,
                "eko",
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name IN ('customer', 'customer_contact') "
                "AND (column_default IS NOT NULL OR is_identity = 'YES')",
            )
            == []
        )
        store, database = store_on(port, password)
        try:
            draft = CustomerDraft(
                name="Gospodarstwo Po Odtworzeniu",
                country="PL",
                contacts=(Contact(ContactKind.PHONE, "+48601000701", None, True),),
            )
            made = [str(store.create(OwnedBy(OWNER), draft).id) for _ in range(5)]
        finally:
            database.dispose()
        assert set(made).isdisjoint(after), "an identifier issued after the set was issued again"
        assert set(made).isdisjoint(before)
        assert all(uuid.UUID(identifier).version == 4 for identifier in made)
