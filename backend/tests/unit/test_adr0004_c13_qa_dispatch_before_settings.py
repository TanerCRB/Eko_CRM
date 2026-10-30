"""R-01 fix (QA, EKO-1-11 verification): env.py refuses a non-head destination before it reads
migrate's own settings, so the refusal is the same in a container that is not migrate.

The application settings are complete and the MIGRATION_* variables are absent, as in the backend
and worker containers. A refused destination still says "migrate refused" and opens nothing.

Contrast (one element changed, the destination): `upgrade head` passes the dispatch and stops on
the missing MIGRATION_* variables instead, so the absent settings are indeed read on that path.
"""

from typing import Any

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config

from tests.support.repo import REPO_ROOT
from tests.unit.conftest import SYNTHETIC_PASSWORD, closed_local_port

MIGRATIONS = REPO_ROOT / "backend" / "migrations"
MIGRATE_ONLY = (
    "MIGRATION_ADVISORY_LOCK_KEY",
    "MIGRATION_LOCK_TIMEOUT_SECONDS",
    "MIGRATION_STATEMENT_TIMEOUT_SECONDS",
)


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    for name, value in {
        "APP_DB_HOST": "127.0.0.1",
        "APP_DB_PORT": str(closed_local_port()),
        "APP_DB_POOL_SIZE": "1",
        "APP_DB_MAX_OVERFLOW": "0",
        "APP_DB_CONNECT_TIMEOUT_SECONDS": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("APP_DB_PASSWORD", SYNTHETIC_PASSWORD)
    for name in MIGRATE_ONLY:
        monkeypatch.delenv(name, raising=False)
    created: list[str] = []
    real = sqlalchemy.create_engine

    def recording(*args: Any, **kwargs: Any) -> Any:
        created.append("engine")
        return real(*args, **kwargs)

    monkeypatch.setattr(sqlalchemy, "create_engine", recording)
    return created


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("path_separator", "os")
    return config


@pytest.mark.parametrize("destination", ["heads", "0001"])
def test_adr0004_c13_qa_refusal_comes_before_migrate_settings(
    engines: list[str], destination: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(), destination)
    assert "migrate refused" in str(stopped.value.code)
    assert engines == []


def test_adr0004_c13_qa_contrast_upgrade_head_reads_migrate_settings(engines: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(), "head")
    message = str(stopped.value.code)
    assert "configuration error" in message
    assert all(name in message for name in MIGRATE_ONLY)
    assert engines == []


def test_adr0004_c13_qa_unknown_destination_is_refused_without_connecting(
    engines: list[str],
) -> None:
    # Alembic resolves an unknown identifier to itself; only a branch form it cannot resolve
    # raises. That is still a destination, not the absence of one.
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(), "zzz@head")
    assert "migrate refused" in str(stopped.value.code)
    assert engines == []
