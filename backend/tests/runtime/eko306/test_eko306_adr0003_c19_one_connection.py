"""EKO-3-06, ADR-0003-C19 as restated (A-7 A): a seed run holds at most one connection to the
application database. The budget counts it as exactly one (`tests/support/db_checks.py`); this is
the seed's own half.

The run logs in as a role PostgreSQL itself limits to one connection, holding the application
role's privileges: a second connection held at the same time would be refused by the server
("too many connections for role"), and the run would fail.

Contrast: with one connection of that role already held by the test, the seed cannot connect and
ends non-success, writing nothing, so the limit does bite.
"""

from collections.abc import Iterator

import psycopg
import pytest

from app.seed_dataset import SHARE_SIZE
from tests.runtime.eko301.conftest import Crm
from tests.runtime.eko306.conftest import Seeder, seeded
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

ONE = "eko306_one_connection"
ONE_PASSWORD = "synthetic-eko306-one"
# Pairs, not a literal mapping: ADR-0004-C9's check reads `NAME: value` as an assignment.
AS_ONE = dict([("APP_DB_USER", ONE), ("APP_DB_PASSWORD", ONE_PASSWORD)])


@pytest.fixture
def one_connection_role(pg: Postgres) -> Iterator[str]:
    with pg.connect() as connection:
        connection.execute(f"DROP ROLE IF EXISTS {ONE}")
        connection.execute(
            f"CREATE ROLE {ONE} LOGIN PASSWORD '{ONE_PASSWORD}' CONNECTION LIMIT 1 INHERIT"
        )
        connection.execute(f"GRANT eko_app TO {ONE}")
    yield ONE
    with pg.connect() as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = %s", (ONE,)
        )
        connection.execute(f"DROP ROLE IF EXISTS {ONE}")


def test_c19_a_seed_run_needs_no_more_than_one_connection(
    crm: Crm, seed: Seeder, one_connection_role: str
) -> None:
    run = seed(env=AS_ONE)
    assert run.code == 0, (run.refusal, run.lines)
    assert len(seeded(crm.pg)) == 3 * SHARE_SIZE


def test_c19_contrast_with_the_one_connection_taken_the_seed_cannot_run(
    crm: Crm, seed: Seeder, one_connection_role: str
) -> None:
    with psycopg.connect(
        host="127.0.0.1", port=crm.pg.port, dbname="eko", user=ONE, password=ONE_PASSWORD
    ):
        run = seed(env=AS_ONE)
    assert run.code != 0
    assert seeded(crm.pg) == []
