"""ADR-0002 session time zone: every application connection runs in UTC (QA, EKO-1-06).

The server's own default is already UTC in the pinned image, so a test that only reads
`SHOW timezone` could not fail when the application stops setting it. The test therefore gives
the application role a non-UTC default in the application database for its duration (a role
setting ranks below a client's startup option), and contrasts:

- a plain connection by the same role with the same credentials and no startup option: the role's
  non-UTC default (proves the fixture is in force);
- a connection from the application's own engine (`app.data.database.create_app_engine`): UTC.
"""

import json

import pytest

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

NON_UTC = "Europe/Warsaw"
SET_ROLE_DEFAULT = f"ALTER ROLE eko_app IN DATABASE eko SET timezone TO '{NON_UTC}'"
RESET_ROLE_DEFAULT = "ALTER ROLE eko_app IN DATABASE eko RESET timezone"

PROBE = """
import json
import psycopg
from sqlalchemy import text
from app.core.settings import Settings, load_settings
from app.data.database import create_app_engine
s = load_settings(Settings)
engine = create_app_engine(s)
with engine.connect() as connection:
    application = connection.execute(text("SHOW timezone")).scalar_one()
engine.dispose()
with psycopg.connect(host=s.app_db_host, port=s.app_db_port, dbname=s.app_db_name,
                     user=s.app_db_user, password=s.app_db_password.get_secret_value()) as conn:
    plain = conn.execute("SHOW timezone").fetchone()[0]
# leftovers-allow: the probe runs inside the backend container and reports its result over stdout
print(json.dumps({"application": application, "plain": plain}))
"""


def test_adr0002_application_connections_use_utc_whatever_the_role_default(
    running: Started,
) -> None:
    composition = running.composition
    composition.sql(SET_ROLE_DEFAULT, "postgres")
    try:
        result = composition.python_in_backend(PROBE)
    finally:
        composition.sql(RESET_ROLE_DEFAULT, "postgres")
    assert result.returncode == 0, result.stderr[-2000:]
    found = json.loads(result.stdout)
    assert found["plain"] == NON_UTC, found
    assert found["application"] == "UTC", found
