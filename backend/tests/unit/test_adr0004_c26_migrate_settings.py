"""K-05 unit half: migrate's lock key and timeouts are read only through the settings, which refuse
a missing, zero or negative timeout (PostgreSQL reads 0 as "no timeout") and a key that is missing,
zero or outside the single-`bigint` range."""

import pytest

from app.core.settings import MigrateSettings, Settings, WebSettings, load_settings

TIMEOUTS = ["MIGRATION_LOCK_TIMEOUT_SECONDS", "MIGRATION_STATEMENT_TIMEOUT_SECONDS"]
KEY = "MIGRATION_ADVISORY_LOCK_KEY"
SYNTHETIC_KEY = "424242"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-migrate-pw")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "1")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "0")
    monkeypatch.setenv(KEY, SYNTHETIC_KEY)
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("MIGRATION_STATEMENT_TIMEOUT_SECONDS", "30")


def test_adr0004_c26_migrate_settings_load(env: None) -> None:
    settings = load_settings(MigrateSettings)
    assert settings.migration_advisory_lock_key == int(SYNTHETIC_KEY)
    assert settings.migration_lock_timeout_seconds == 5
    assert settings.migration_statement_timeout_seconds == 30


@pytest.mark.parametrize("name", TIMEOUTS)
@pytest.mark.parametrize("value", [None, "", "0", "-1", "-30", "five"])
def test_adr0004_c26_migrate_settings_refuse_a_missing_zero_or_negative_timeout(
    env: None, monkeypatch: pytest.MonkeyPatch, name: str, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as stopped:
        load_settings(MigrateSettings)
    assert name in str(stopped.value.code)


@pytest.mark.parametrize(
    "value", [None, "", "0", "9223372036854775808", "-9223372036854775809", "key"]
)
def test_adr0004_c26_migrate_settings_refuse_a_missing_zero_or_out_of_range_key(
    env: None, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(KEY)
    else:
        monkeypatch.setenv(KEY, value)
    with pytest.raises(SystemExit) as stopped:
        load_settings(MigrateSettings)
    assert KEY in str(stopped.value.code)


@pytest.mark.parametrize("value", ["9223372036854775807", "-9223372036854775808", "-1"])
def test_adr0004_c26_migrate_settings_accept_every_non_zero_bigint_key(
    env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(KEY, value)
    assert load_settings(MigrateSettings).migration_advisory_lock_key == int(value)


@pytest.mark.parametrize("cls", [Settings, WebSettings])
def test_adr0004_c26_backend_and_worker_settings_carry_no_lock_or_timeout(
    cls: type[Settings],
) -> None:
    names = {name.upper() for name in cls.model_fields}
    assert names & {KEY, *TIMEOUTS} == set()
