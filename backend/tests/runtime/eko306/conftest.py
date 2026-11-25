"""EKO-3-06 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, and the operator seed
run against the same server: in-process through `app.seed.run`, where a test injects records
(C-4 A) and reads the report and every log record, or as the operator runs it,
`python -m app.seed <subject> <subject> <subject>`, in a process of its own.

Every value is synthetic (ADR-0005); every NIP and phone is built at run time.
"""

import logging
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from psycopg import sql

from app import seed as seed_module
from app.seed_dataset import Record
from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko303.conftest import new_database, rows_of, run_migrate
from tests.support.pg_instance import BACKEND, Postgres

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers
crm = eko301.crm

DECLARATION = "APP_SYNTHETIC_DATA_ONLY"
DECLARED = "declared"
SEED_A = "5a1e0306-0000-4000-8000-00000000000a"
SEED_B = "5a1e0306-0000-4000-8000-00000000000b"
SEED_C = "5a1e0306-0000-4000-8000-00000000000c"
# The contrast's replacement for B (K-01), and a subject owning a pre-existing customer (K-06).
SEED_B_PRIME = "5a1e0306-0000-4000-8000-0000000000b2"
UNNAMED = "5a1e0306-0000-4000-8000-0000000000ee"
SUBJECTS = (SEED_A, SEED_B, SEED_C)
REFUSED_LINE = re.compile(
    r"record (?P<key>\S+) refused: (?P<family>CUS-[0-9]+(?:/CUS-[0-9]+)?) \((?P<field>[a-z_.]+)\)"
)
FINISHED = re.compile(
    r"seed finished: (?P<total>[0-9]+) records, (?P<added>[0-9]+) added, "
    r"(?P<already>[0-9]+) already loaded, (?P<refused>[0-9]+) refused"
)


def seed_env(
    pg: Postgres, database: str = "eko", declared: str | None = DECLARED
) -> dict[str, str]:
    """The worker's environment for a one-off on the test's server: its pool values (2, 0)."""
    env = {**pg.app_env(2, 0), "APP_DB_NAME": database}
    if declared is not None:
        env[DECLARATION] = declared
    return env


@dataclass
class SeedRun:
    """What one run gave the operator: the exit status (0 is success), the refusal message of a
    run refused at start, and every line the seed's logger wrote."""

    code: int
    refusal: str | None
    lines: list[str] = field(default_factory=list)

    def refused(self) -> dict[str, tuple[str, str]]:
        found = {}
        for line in self.lines:
            match = REFUSED_LINE.fullmatch(line)
            if match:
                found[match["key"]] = (match["family"], match["field"])
        return found

    def totals(self) -> dict[str, int]:
        [match] = [m for m in map(FINISHED.match, self.lines) if m]
        return {k: int(v) for k, v in match.groupdict().items()}


class Seeder:
    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, pg: Postgres
    ) -> None:
        self.monkeypatch = monkeypatch
        self.caplog = caplog
        self.pg = pg

    def __call__(
        self,
        subjects: Sequence[str] = SUBJECTS,
        records: Sequence[Record] | None = None,
        database: str = "eko",
        declared: str | None = DECLARED,
        env: dict[str, str] | None = None,
    ) -> SeedRun:
        """One in-process run; `env` replaces values of the worker's environment."""
        for name, value in {**seed_env(self.pg, database, declared), **(env or {})}.items():
            self.monkeypatch.setenv(name, value)
        if declared is None:
            self.monkeypatch.delenv(DECLARATION, raising=False)
        self.caplog.set_level(logging.DEBUG, logger="app.seed")
        start = len(self.caplog.records)
        refusal = None
        try:
            code = seed_module.run(list(subjects), records)
        except SystemExit as stopped:
            refusal = str(stopped.code)
            code = 1 if not isinstance(stopped.code, int) else stopped.code
        lines = [
            r.getMessage() for r in self.caplog.records[start:] if r.name.startswith("app.seed")
        ]
        return SeedRun(code, refusal, lines)


@pytest.fixture
def seed(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, pg: Postgres) -> Seeder:
    return Seeder(monkeypatch, caplog, pg)


def seed_process(
    pg: Postgres,
    subjects: Sequence[str] = SUBJECTS,
    database: str = "eko",
    declared: str | None = DECLARED,
    hash_seed: str = "0",
) -> subprocess.CompletedProcess[str]:
    """`python -m app.seed ...` as the operator's one-off runs it, with the worker's environment
    and nothing of the test process's own application settings."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("APP_")}
    env.update(seed_env(pg, database, declared))
    env["PYTHONHASHSEED"] = hash_seed
    return subprocess.run(
        [sys.executable, "-m", "app.seed", *subjects],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        check=False,
    )


def fresh_database(pg: Postgres, name: str) -> None:
    """A new database on the test's server, migrated to this tree's head as `migrate` runs."""
    new_database(pg, name)
    code, output = run_migrate(pg, name)
    assert code == 0, output[-2000:]


def tables(pg: Postgres, database: str) -> list[str]:
    found = rows_of(
        pg, database, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
    )
    return [str(row[0]) for row in found]


def snapshot(pg: Postgres, database: str = "eko") -> dict[str, list[str]]:
    """Every row of every table of the application database, as PostgreSQL writes it as text."""
    found = {}
    for table in tables(pg, database):
        query = sql.SQL("SELECT t::text FROM {} t ORDER BY 1").format(sql.Identifier(table))
        found[table] = [str(row[0]) for row in rows_of(pg, database, query.as_string())]
    return found


SCHEMA_QUERIES = (
    "SELECT table_name, column_name, data_type, is_nullable, column_default, collation_name "
    "FROM information_schema.columns WHERE table_schema = 'public' ORDER BY 1, 2",
    "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2",
    "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
    "ORDER BY 1, 2",
)


def schema(pg: Postgres, database: str = "eko") -> list[list[tuple[Any, ...]]]:
    return [rows_of(pg, database, query) for query in SCHEMA_QUERIES]


def seeded(pg: Postgres, database: str = "eko") -> list[tuple[Any, ...]]:
    """`(id, dataset_key, owner_subject)` of every seeded customer, by dataset key."""
    return rows_of(
        pg,
        database,
        "SELECT id::text, dataset_key, owner_subject FROM customer "
        "WHERE dataset_key IS NOT NULL ORDER BY dataset_key",
    )
