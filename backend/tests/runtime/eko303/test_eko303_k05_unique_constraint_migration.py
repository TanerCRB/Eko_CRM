"""EKO-3-03 K-05 (ADR-0002-C9 as written; ADR-0004 *Expand -> deploy -> contract* and C14; G-2 A,
G-6 A; the gate-1 addendum draft, sections 1 and 2): revision 0007 is a contract step adding one
unique constraint on `customer.nip` and nothing else; through SQL a second equal `nip` is a unique
violation while NULLs and equal foreign tax IDs stay allowed; and over stored duplicates the
revision refuses the run naming only their count, changing nothing.

Each migration case has a database of its own on the test's server, brought to 0006 by this tree
with revision 0007's file left out, then migrated by this tree as `migrate` runs. The previous
release on the new head is `tests/runtime/test_eko303_k05_previous_release_on_0007.py`.
"""

import subprocess
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.runtime.eko301.conftest import REP_A, Crm
from tests.runtime.eko303.conftest import (
    NIP_CONSTRAINT,
    PREVIOUS,
    REVISION,
    ROWS,
    at_previous,
    connect_to,
    migrate_command,
    plant,
    refused_count,
    rows_of,
    run_migrate,
    versions,
)
from tests.support import eko302_nip as nips
from tests.support.pg_instance import MIGRATE_ENV, Postgres

pytestmark = pytest.mark.runtime

DATABASE = "eko_k05"
INSERT = (
    "INSERT INTO customer (id, name, country, owner_subject, nip, foreign_tax_id) "
    "VALUES (%s, 'Gospodarstwo C9', %s, %s, %s, %s)"
)
LOCK_KEY = int(MIGRATE_ENV["MIGRATION_ADVISORY_LOCK_KEY"])
WAITING = "SELECT count(*) FROM pg_locks WHERE locktype = %s AND NOT granted"


def insert(crm: Crm, country: str, nip: Any, foreign: Any) -> None:
    with crm.pg.connect() as connection:
        connection.execute(INSERT, (uuid.uuid4(), country, REP_A, nip, foreign))


def leaked(output: str, *values: str) -> list[str]:
    forms = {form for value in values for form in (value, nips.hyphenated(value))}
    return sorted(form for form in forms if form in output)


def constraint(pg: Postgres, database: str) -> list[tuple[Any, ...]]:
    return rows_of(pg, database, NIP_CONSTRAINT)


# (1) ADR-0002-C9 as written, through SQL past the services --------------------------------------


def test_k05_c9_a_second_customer_with_an_existing_nip_is_a_unique_violation(crm: Crm) -> None:
    nip = nips.valid_nip(35101)
    insert(crm, "PL", nip, None)
    with pytest.raises(psycopg.errors.UniqueViolation) as raised:
        insert(crm, "PL", nip, None)
    assert raised.value.sqlstate == "23505"
    assert raised.value.diag.constraint_name == "uq_customer_nip"
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE nip = %s", (nip,)) == [(1,)]


@pytest.mark.parametrize(
    "nip",
    [
        pytest.param(lambda: "PL" + nips.valid_nip(35202), id="pl-prefix"),
        pytest.param(lambda: "DE123456789", id="foreign-value"),
    ],
)
def test_k05_c9_a_nip_that_is_not_ten_digits_is_a_check_violation(crm: Crm, nip: Any) -> None:
    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(crm, "PL", nip(), None)
    assert raised.value.sqlstate == "23514"


def test_k05_c9_two_customers_without_a_nip_and_two_with_one_foreign_tax_id_are_stored(
    crm: Crm,
) -> None:
    insert(crm, "PL", None, None)
    insert(crm, "PL", None, None)
    insert(crm, "DE", None, "DE123456789")
    insert(crm, "DE", None, "DE123456789")
    assert crm.counts()["customer"] == 4


def test_k05_c9_the_constraint_is_unique_on_nip_alone_with_nulls_distinct(crm: Crm) -> None:
    assert crm.pg.rows(NIP_CONSTRAINT) == [("u", "UNIQUE (nip)", False)]
    unique_on_foreign = crm.pg.rows(
        "SELECT count(*) FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
        "AND a.attnum = ANY (i.indkey) WHERE i.indrelid = 'customer'::regclass "
        "AND i.indisunique AND a.attname = 'foreign_tax_id'"
    )
    assert unique_on_foreign == [(0,)]


# (2) The schema diff between 0006 and the new head ---------------------------------------------


def schema(pg: Postgres, database: str) -> Counter[str]:
    """`pg_dump --schema-only` as lines, without comments, blank lines and the per-run
    `\\restrict` key, counted so a repeated line is compared too."""
    dump = subprocess.run(
        ["docker", "exec", pg.container, "pg_dump", "-U", "postgres", "--schema-only", database],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )  # fmt: skip
    kept = (
        line
        for line in dump.stdout.splitlines()
        if line.strip() and not line.startswith(("--", "\\restrict", "\\unrestrict"))
    )
    return Counter(kept)


def test_k05_the_schema_diff_from_0006_is_one_unique_constraint_on_nip(
    pg: Postgres, tmp_path: Path
) -> None:
    at_previous(pg, DATABASE, tmp_path)
    before = schema(pg, DATABASE)
    code, output = run_migrate(pg, DATABASE)
    assert code == 0, output[-2000:]
    after = schema(pg, DATABASE)
    assert after - before == Counter(
        ["ALTER TABLE ONLY public.customer", "    ADD CONSTRAINT uq_customer_nip UNIQUE (nip);"]
    )
    assert before - after == Counter()
    assert versions(pg, DATABASE) == [REVISION]


# (3) G-2 A: over stored duplicates the revision refuses and changes nothing --------------------


def test_k05_migrate_over_a_duplicate_pair_refuses_with_the_count_and_changes_nothing(
    pg: Postgres, tmp_path: Path
) -> None:
    dup, single = nips.valid_nip(35303), nips.valid_nip(35404)
    at_previous(pg, DATABASE, tmp_path)
    plant(pg, DATABASE, ("PL", dup, None), ("PL", dup, None), ("PL", single, None))
    before = rows_of(pg, DATABASE, ROWS)

    code, output = run_migrate(pg, DATABASE)

    assert code != 0, output[-2000:]
    assert refused_count(output) == 1, output[-2000:]
    assert versions(pg, DATABASE) == [PREVIOUS]
    assert constraint(pg, DATABASE) == []
    assert rows_of(pg, DATABASE, ROWS) == before
    assert leaked(output, dup, single) == []


def test_k05_the_count_is_the_number_of_nip_values_held_more_than_once(
    pg: Postgres, tmp_path: Path
) -> None:
    three, two, one = nips.valid_nip(35505), nips.valid_nip(35606), nips.valid_nip(35707)
    at_previous(pg, DATABASE, tmp_path)
    plant(
        pg, DATABASE, ("PL", three, None), ("PL", three, None), ("PL", three, None),
        ("PL", two, None), ("PL", two, None), ("PL", one, None), ("PL", None, None),
        ("PL", None, None),
    )  # fmt: skip
    before = rows_of(pg, DATABASE, ROWS)
    code, output = run_migrate(pg, DATABASE)
    assert code != 0, output[-2000:]
    assert refused_count(output) == 2, output[-2000:]
    assert versions(pg, DATABASE) == [PREVIOUS]
    assert rows_of(pg, DATABASE, ROWS) == before
    assert leaked(output, three, two, one) == []


def test_k05_contrast_distinct_nips_nulls_and_equal_foreign_tax_ids_reach_the_new_head(
    pg: Postgres, tmp_path: Path
) -> None:
    first, second = nips.valid_nip(35808), nips.valid_nip(35909)
    at_previous(pg, DATABASE, tmp_path)
    plant(
        pg, DATABASE, ("PL", first, None), ("PL", second, None), ("PL", None, None),
        ("PL", None, None), ("DE", None, "DE123456789"), ("DE", None, "DE123456789"),
    )  # fmt: skip
    before = rows_of(pg, DATABASE, ROWS)
    code, output = run_migrate(pg, DATABASE)
    assert code == 0, output[-2000:]
    assert refused_count(output) is None
    assert versions(pg, DATABASE) == [REVISION]
    assert constraint(pg, DATABASE) == [("u", "UNIQUE (nip)", False)]
    assert rows_of(pg, DATABASE, ROWS) == before


def test_k05_an_empty_customer_table_migrates(pg: Postgres, tmp_path: Path) -> None:
    at_previous(pg, DATABASE, tmp_path)
    code, output = run_migrate(pg, DATABASE)
    assert code == 0, output[-2000:]
    assert versions(pg, DATABASE) == [REVISION]
    assert constraint(pg, DATABASE) == [("u", "UNIQUE (nip)", False)]


# A duplicate written while `migrate` waits for its lock -----------------------------------------


def wait_for(pg: Postgres, database: str, lock_type: str, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while rows_of(pg, database, WAITING, (lock_type,)) != [(1,)]:
        if time.monotonic() > deadline:
            raise AssertionError(f"migrate never waited on a {lock_type} lock")
        time.sleep(0.05)


def test_k05_a_duplicate_stored_while_migrate_waits_for_its_lock_is_counted(
    pg: Postgres, tmp_path: Path
) -> None:
    dup = nips.valid_nip(36101)
    at_previous(pg, DATABASE, tmp_path)
    plant(pg, DATABASE, ("PL", dup, None))
    with connect_to(pg, DATABASE) as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        run = subprocess.Popen(**migrate_command(pg, DATABASE))
        try:
            wait_for(pg, DATABASE, "advisory")
            plant(pg, DATABASE, ("PL", dup, None))
            holder.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
            output, _ = run.communicate(timeout=120)
        finally:
            run.kill()
    assert run.returncode != 0, output[-2000:]
    assert refused_count(output) == 1, output[-2000:]
    assert versions(pg, DATABASE) == [PREVIOUS]
    assert rows_of(pg, DATABASE, "SELECT count(*) FROM customer WHERE nip = %s", (dup,)) == [(2,)]
    assert leaked(output, dup) == []


def test_k05_a_duplicate_committed_after_the_count_is_refused_by_the_constraint(
    pg: Postgres, tmp_path: Path
) -> None:
    dup = nips.valid_nip(36202)
    at_previous(pg, DATABASE, tmp_path)
    plant(pg, DATABASE, ("PL", dup, None))
    with connect_to(pg, DATABASE) as holder, connect_to(pg, DATABASE) as writer:
        holder.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        run = subprocess.Popen(**migrate_command(pg, DATABASE))
        try:
            wait_for(pg, DATABASE, "advisory")
            writer.execute("BEGIN")
            writer.execute(
                "INSERT INTO customer (id, name, country, owner_subject, nip) "
                "VALUES (%s, 'Gospodarstwo K05 wyscig', 'PL', %s, %s)",
                (uuid.uuid4(), REP_A, dup),
            )
            holder.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
            # The count cannot see the uncommitted row; the DDL then waits for the writer.
            wait_for(pg, DATABASE, "relation")
            writer.execute("COMMIT")
            output, _ = run.communicate(timeout=120)
        finally:
            run.kill()
    assert run.returncode != 0, output[-2000:]
    assert refused_count(output) is None, output[-2000:]
    assert "UniqueViolation" in output, output[-2000:]
    assert versions(pg, DATABASE) == [PREVIOUS]
    assert constraint(pg, DATABASE) == []
    assert rows_of(pg, DATABASE, "SELECT count(*) FROM customer WHERE nip = %s", (dup,)) == [(2,)]
    assert leaked(output, dup) == []
