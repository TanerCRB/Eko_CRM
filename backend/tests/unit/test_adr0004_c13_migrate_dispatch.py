"""R-01 / L-01 (EKO-1-11 verification): env.py runs migrations only for `alembic upgrade head`.

The real env.py is run through Alembic's own command API, so each destination is resolved exactly
as the CLI resolves it (`heads` to a tuple, `base` to None). The database is a closed local port:
a refused command never opens a connection, while the two contrasts reach the database and fail
there, which shows they passed the dispatch.
"""

from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config

from tests.support.repo import REPO_ROOT
from tests.unit.conftest import SYNTHETIC_PASSWORD, closed_local_port

MIGRATIONS = REPO_ROOT / "backend" / "migrations"


@pytest.fixture
def connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    for name, value in {
        "APP_DB_HOST": "127.0.0.1",
        "APP_DB_PORT": str(closed_local_port()),
        "APP_DB_POOL_SIZE": "1",
        "APP_DB_MAX_OVERFLOW": "0",
        "APP_DB_CONNECT_TIMEOUT_SECONDS": "1",
        "MIGRATION_ADVISORY_LOCK_KEY": "424242",
        "MIGRATION_LOCK_TIMEOUT_SECONDS": "5",
        "MIGRATION_STATEMENT_TIMEOUT_SECONDS": "30",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("APP_DB_PASSWORD", SYNTHETIC_PASSWORD)
    opened: list[str] = []
    real = sqlalchemy.create_engine

    def recording(*args: Any, **kwargs: Any) -> Any:
        opened.append("engine")
        return real(*args, **kwargs)

    # env.py is executed afresh by Alembic and imports create_engine from sqlalchemy each time.
    monkeypatch.setattr(sqlalchemy, "create_engine", recording)
    return opened


def alembic_config() -> Config:
    # No file name, so env.py does not reconfigure logging inside the test process.
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("path_separator", "os")
    return config


REFUSED: dict[str, Callable[[Config], None]] = {
    "upgrade heads": lambda c: command.upgrade(c, "heads"),
    "upgrade 0001 (not the head)": lambda c: command.upgrade(c, "0001"),
    "upgrade +1 (relative)": lambda c: command.upgrade(c, "+1"),
    "downgrade base": lambda c: command.downgrade(c, "base"),
    "downgrade -1": lambda c: command.downgrade(c, "-1"),
    "downgrade 0001": lambda c: command.downgrade(c, "0001"),
}


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_adr0004_c13_migrate_dispatch_refuses_every_destination_but_head(
    connections: list[str], case: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        REFUSED[case](alembic_config())
    assert "migrate refused" in str(stopped.value.code)
    assert connections == []


def test_adr0004_c13_migrate_dispatch_contrast_upgrade_head_reaches_the_database(
    connections: list[str],
) -> None:
    with pytest.raises(sqlalchemy.exc.OperationalError):
        command.upgrade(alembic_config(), "head")
    assert connections == ["engine"]


def test_adr0004_c13_migrate_dispatch_contrast_current_has_no_destination_and_reads(
    connections: list[str],
) -> None:
    with pytest.raises(sqlalchemy.exc.OperationalError):
        command.current(alembic_config())
    assert connections == ["engine"]
