"""EKO-1-10 K-03: each guarded backend call appears only in its one allowed place.

ADR-0001-C10, ADR-0002-C13 and C4 as restated 2026-10-29; the migrations half of ADR-0001-C6.
"""

from collections.abc import Callable

import pytest

from tests.support import source_checks as sc

Check = Callable[[sc.Files], list[str]]
SERVICES = "backend/app/services/x.py"
MIGRATION = "backend/migrations/versions/0002_x.py"


def fails(check: Check, path: str, text: str) -> bool:
    return check({path: text}) != []


# ADR-0001-C10 ----------------------------------------------------------------------------------

ENV_READS = [
    "import os\nHOST = os.environ['APP_DB_HOST']\n",
    "import os\nHOST = os.environ.get('X')\n",
    "from os import environ\n",
    "from os import environ as env\n",
    "from os import (\n    path,\n    environ,\n)\n",
    "import os\nX = os.getenv('X')\n",
    "from os import getenv\n",
    "import os\nos.putenv('X', 'y')\n",
    "import os\nX = os.environb\n",
    "import os\nX = os.getenvb(b'X')\n",
    "from os import getenvb\n",
    "from pydantic_settings import SettingsConfigDict\n",
    "from app.core.settings import BaseSettings\n\n\nclass Extra(BaseSettings):\n    x: int = 1\n",
    "from dotenv import load_dotenv\n",
    "import dotenv\n",
    "from starlette.config import Config\n",
    "from starlette.config import environ\n",
    "from starlette import config\n",
    "import starlette.config\n",
    '"""Reads os.environ in a docstring."""\n',
    "# os.getenv in a comment\n",
    "import os\r\nX = os.environ\r\n",
]


def test_eko110_k03_env_reads_only_in_settings() -> None:
    assert sc.env_reads(sc.repository_sources()) == []


@pytest.mark.parametrize("text", ENV_READS)
def test_eko110_k03_env_read_fails_outside_settings(text: str) -> None:
    assert fails(sc.env_reads, SERVICES, text)


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/core/settings_extra.py",
        "backend/app/core/x.py",
        "backend/app/main.py",
        "backend/app/services/fixtures/x.py",
        "backend/app/core/settings/x.py",
    ],
)
def test_eko110_k03_env_read_twins_of_settings_are_not_exempt(path: str) -> None:
    assert fails(sc.env_reads, path, "import os\nX = os.getenv('X')\n")


def test_eko110_k03_env_contrasts_pass() -> None:
    text = (
        '"""Reads the environment name from settings."""\n\n'
        "from pydantic import BaseModel, ConfigDict\n\n\n"
        "class Status(BaseModel):\n"
        '    model_config = ConfigDict(extra="forbid")\n'
        "    environment_name: str = 'environment'\n"
    )
    assert sc.env_reads({SERVICES: text}) == []
    assert sc.env_reads({"backend/app/core/settings.py": "import os\nX = os.environ\n"}) == []
    assert sc.env_reads({"backend/tests/x.py": "import os\nX = os.environ\n"}) == []


# ADR-0002-C13 ----------------------------------------------------------------------------------

CLOCK_READS = [
    "import datetime\nX = datetime.datetime.now(tz=datetime.UTC)\n",
    "from datetime import datetime\nX = datetime.utcnow()\n",
    "from datetime import date\nX = date.today()\n",
    "from datetime import datetime\nX = datetime.today()\n",
    "import time\nX = time.time()\n",
    "import time\nX = time.time_ns()\n",
    "import time\nX = time.localtime()\n",
    "import sqlalchemy as sa\nX = sa.func.now()\n",
    "import sqlalchemy as sa\nX = sa.func.clock_timestamp()\n",
    'X = "SELECT clock_timestamp()"\n',
    'X = "SELECT statement_timestamp()"\n',
    'X = "SELECT transaction_timestamp()"\n',
    'X = "SELECT timeofday()"\n',
    "X = \"SELECT 'now'::timestamptz\"\n",
    "X = \"SELECT 'NOW'::timestamptz\"\n",
    "X = \"SELECT 'today'::date\"\n",
    "X = \"SELECT 'now'::date\"\n",
    "X = \"SELECT 'today'::timestamp\"\n",
    "X = \"SELECT 'tomorrow'\"\n",
    "X = \"SELECT 'yesterday'\"\n",
    "X = \"SELECT CAST('now' AS date)\"\n",
    'X = "SELECT CURRENT_DATE"\n',
    'X = "SELECT current_timestamp"\n',
    'X = "SELECT LOCALTIMESTAMP"\n',
    'X = "SELECT now()"\n',
    'server_default = "now()"\n',
    '"""Uses datetime.now( in a docstring."""\n',
    'X = 1\r\nY = "SELECT CURRENT_DATE"\r\n',
]


def test_eko110_k03_clock_reads_only_in_clock() -> None:
    assert sc.clock_reads(sc.repository_sources()) == []


@pytest.mark.parametrize("text", CLOCK_READS)
@pytest.mark.parametrize("path", [SERVICES, "backend/app/data/models.py", MIGRATION])
def test_eko110_k03_clock_read_fails_outside_clock(path: str, text: str) -> None:
    assert fails(sc.clock_reads, path, text)


def test_eko110_k03_server_default_from_the_database_clock_fails_in_a_migration() -> None:
    line = 'sa.Column("visited_on", sa.Date(), server_default=sa.text("CURRENT_DATE"))\n'
    assert fails(
        sc.clock_reads,
        MIGRATION,
        'def upgrade() -> None:\n    op.execute("UPDATE t SET x = now()")\n',
    )
    assert fails(sc.clock_reads, "backend/migrations/versions/0001_baseline.py", line)
    assert fails(sc.clock_reads, "backend/app/data/models.py", line)
    assert sc.clock_reads({"backend/app/core/clock.py": line}) == []


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/core/clock_utils.py",
        "backend/app/core/x.py",
        "backend/app/core/clock/x.py",
        "backend/migrations/clock.py",
        "backend/app/services/fixtures/x.py",
    ],
)
def test_eko110_k03_clock_twins_are_not_exempt(path: str) -> None:
    assert fails(sc.clock_reads, path, "import time\nX = time.time()\n")


def test_eko110_k03_clock_contrasts_pass() -> None:
    text = (
        '"""Baseline.\n\nRevision ID: 0002\nCreate Date: 2026-10-28\n"""\n\n'
        "import datetime\n\nOPENS = datetime.time(9, 0)\n\n\n"
        "def at(dt: datetime.datetime) -> datetime.time:\n    return dt.time()\n"
    )
    assert sc.clock_reads({MIGRATION: text, SERVICES: text}) == []


# ADR-0002-C4 ----------------------------------------------------------------------------------


def test_eko110_k03_sqlalchemy_only_in_data() -> None:
    assert sc.sqlalchemy_outside_data(sc.repository_sources()) == []
    for path in (
        SERVICES,
        "backend/app/api/health.py",
        "backend/app/main.py",
        "backend/app/data_export/x.py",
        "backend/app/services/fixtures/x.py",
    ):
        assert fails(sc.sqlalchemy_outside_data, path, "from sqlalchemy import text\n"), path
    assert fails(sc.sqlalchemy_outside_data, SERVICES, "import sqlalchemy\n")
    assert (
        sc.sqlalchemy_outside_data({"backend/app/data/x.py": "from sqlalchemy import text\n"}) == []
    )
    assert sc.sqlalchemy_outside_data({"backend/app/data/sub/x.py": "import sqlalchemy\n"}) == []


def test_eko110_k03_no_schema_creation() -> None:
    assert sc.schema_creation(sc.repository_sources()) == []
    for path in ("backend/app/data/models.py", "backend/migrations/env.py", MIGRATION, SERVICES):
        for call in ("Base.metadata.create_all(engine)\n", "Base.metadata.drop_all(engine)\n"):
            assert fails(sc.schema_creation, path, call), (path, call)
    assert sc.schema_creation({"backend/tests/x.py": "Base.metadata.create_all(engine)\n"}) == []


# ADR-0001-C6, migrations half ------------------------------------------------------------------

PASSWORD_COLUMNS = [
    'sa.Column("password_hash", sa.String())\n',
    'sa.Column("PASSWD", sa.String())\n',
    'sa.Column("user_password", sa.String())\n',
    'sa.Column("Password", sa.String())\n',
    'op.add_column("staff", sa.Column("passwd", sa.Text()))\n',
    'op.execute("ALTER TABLE staff ADD COLUMN password text")\n',
    "class Staff:\n    password = sa.Column(sa.String())\n",
    'sa.Column("x", sa.String())\r\nsa.Column("password", sa.String())\r\n',
]


def test_eko110_k03_no_password_column_in_migrations() -> None:
    assert sc.password_columns(sc.repository_sources()) == []


@pytest.mark.parametrize("text", PASSWORD_COLUMNS)
def test_eko110_k03_password_column_fails_in_a_migration(text: str) -> None:
    assert fails(sc.password_columns, MIGRATION, text)


def test_eko110_k03_password_contrasts_pass() -> None:
    text = (
        '"""Adds display names; no password is stored (ADR-0003)."""\n\n'
        "# The password stays in Keycloak.\n"
        'COLUMN = sa.Column("display_name", sa.String())\n'
    )
    assert sc.password_columns({MIGRATION: text}) == []
    assert sc.password_columns({"backend/app/data/x.py": 'sa.Column("password")\n'}) == []
