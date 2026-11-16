"""EKO-2-01 schema (revision 0003): the session and login-transaction tables as migrate creates
them on real PostgreSQL. ADR-0002-C3 (`alembic check`), ADR-0002-C6 (instants are
`timestamp with time zone`), ADR-0003-C13 (no staff e-mail, username or credential column), and
the stored session identifier is a hash, never the cookie's value.
"""

import os
import subprocess
import sys

import pytest

from tests.support.pg_instance import BACKEND, Postgres

pytestmark = pytest.mark.runtime


def test_eko201_schema_matches_the_models(pg: Postgres) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND,
        env={**os.environ, **pg.app_env(1, 0)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]


def test_eko201_tables_exist_with_aware_instants_only(pg: Postgres) -> None:
    columns = pg.rows(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name IN ('app_session', 'login_transaction')"
    )
    assert {(t, c) for t, c, _ in columns} >= {
        ("app_session", "session_hash"),
        ("app_session", "tokens"),
        ("app_session", "created_at"),
        ("app_session", "last_used_at"),
        ("login_transaction", "state_hash"),
        ("login_transaction", "created_at"),
    }
    assert [(t, c) for t, c, kind in columns if kind == "timestamp without time zone"] == []


def test_eko201_no_staff_email_username_or_credential_column(pg: Postgres) -> None:
    names = [c for (c,) in pg.rows(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public'"
    )]  # fmt: skip
    forbidden = ("mail", "user", "passw", "credential", "login_name")
    assert [n for n in names if any(f in n.lower() for f in forbidden)] == []
