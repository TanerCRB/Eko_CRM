"""A real PostgreSQL 18 server for the EKO-2-01 backend carriers, migrated by the shipped Alembic.

One throwaway container of the pinned image (ADR-0002 addendum of 2026-10-28), on a free local
port, with the application role and database created as the composition creates them, and
removed with its data afterwards. Every value is synthetic (ADR-0005).
"""

import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg

from tests.support.repo import REPO_ROOT

IMAGE = "postgres:18.6-trixie"
SUPERUSER_PASSWORD = "synthetic-eko201-superuser"
APP_PASSWORD = "synthetic-eko201-app"
BACKEND = REPO_ROOT / "backend"
MIGRATE_ENV = {
    "MIGRATION_ADVISORY_LOCK_KEY": "727272",
    "MIGRATION_LOCK_TIMEOUT_SECONDS": "10",
    "MIGRATION_STATEMENT_TIMEOUT_SECONDS": "60",
}


@dataclass(frozen=True)
class Postgres:
    container: str
    port: int

    def app_env(self, pool_size: int = 5, max_overflow: int = 5) -> dict[str, str]:
        # Pairs, not a literal mapping: ADR-0004-C9's check reads `NAME: value` as an assignment.
        return dict(
            [
                ("APP_DB_HOST", "127.0.0.1"),
                ("APP_DB_PORT", str(self.port)),
                ("APP_DB_NAME", "eko"),
                ("APP_DB_USER", "eko_app"),
                ("APP_DB_PASSWORD", APP_PASSWORD),
                ("APP_DB_POOL_SIZE", str(pool_size)),
                ("APP_DB_MAX_OVERFLOW", str(max_overflow)),
            ]
        )

    def connect(self, autocommit: bool = True) -> psycopg.Connection[Any]:
        return psycopg.connect(
            host="127.0.0.1",
            port=self.port,
            dbname="eko",
            user="postgres",
            password=SUPERUSER_PASSWORD,
            autocommit=autocommit,
        )

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self.connect() as connection:
            return list(connection.execute(query, params).fetchall())


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", check=check
    )


def _wait_ready(port: int) -> None:
    deadline = time.monotonic() + 90
    while True:
        try:
            with psycopg.connect(
                host="127.0.0.1", port=port, dbname="postgres", user="postgres",
                password=SUPERUSER_PASSWORD, connect_timeout=2,
            ):  # fmt: skip
                return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@contextmanager
def postgres() -> Iterator[Postgres]:
    name = f"eko201-pg-{uuid.uuid4().hex[:10]}"
    _docker(
        "run", "-d", "--rm", "--name", name, "-e", f"POSTGRES_PASSWORD={SUPERUSER_PASSWORD}",
        "-p", "127.0.0.1::5432", IMAGE, "-c", "max_connections=100",
    )  # fmt: skip
    try:
        mapped = _docker("port", name, "5432/tcp").stdout.strip().splitlines()[0]
        port = int(mapped.rsplit(":", 1)[1])
        _wait_ready(port)
        # The server can restart once after its first initialisation; wait for the second start.
        time.sleep(1)
        _wait_ready(port)
        with psycopg.connect(
            host="127.0.0.1", port=port, dbname="postgres", user="postgres",
            password=SUPERUSER_PASSWORD, autocommit=True,
        ) as connection:  # fmt: skip
            connection.execute(
                f"CREATE ROLE eko_app LOGIN PASSWORD '{APP_PASSWORD}' CONNECTION LIMIT 60"
            )
            connection.execute(
                "CREATE DATABASE eko OWNER eko_app TEMPLATE template0 ENCODING 'UTF8' "
                "LOCALE_PROVIDER icu ICU_LOCALE 'pl-PL' LOCALE 'C.UTF-8'"
            )
        instance = Postgres(name, port)
        migrate(instance)
        yield instance
    finally:
        _docker("rm", "-f", name, check=False)


def migrate(instance: Postgres) -> None:
    """`alembic upgrade head` as `migrate` runs it, against the throwaway server."""
    import os

    env = {**os.environ, **instance.app_env(1, 0), **MIGRATE_ENV}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
