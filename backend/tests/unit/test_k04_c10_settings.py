"""K-04 / ADR-0004-C10, backend half: a missing or empty secret stops the component."""

import pytest
from pydantic import SecretStr

from app.core.settings import Settings, load_settings

SECRETS = ["APP_DB_PASSWORD"]
VALUE = "synthetic-secret-value-91c2"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_PASSWORD", VALUE)
    monkeypatch.setenv("APP_DB_POOL_SIZE", "5")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "5")


def test_k04_c10_settings_load_with_every_required_variable(env: None) -> None:
    settings = load_settings(Settings)
    assert settings.app_db_password.get_secret_value() == VALUE


@pytest.mark.parametrize("name", SECRETS)
def test_k04_c10_unset_secret_stops_naming_the_variable(
    env: None, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)
    with pytest.raises(SystemExit) as stopped:
        load_settings(Settings)
    assert name in str(stopped.value.code)


@pytest.mark.parametrize("name", SECRETS)
@pytest.mark.parametrize("empty", ["", "   "])
def test_k04_c10_empty_secret_stops_naming_the_variable(
    env: None, monkeypatch: pytest.MonkeyPatch, name: str, empty: str
) -> None:
    monkeypatch.setenv(name, empty)
    with pytest.raises(SystemExit) as stopped:
        load_settings(Settings)
    assert name in str(stopped.value.code)


def test_k04_c10_stop_message_holds_no_value(env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DB_POOL_SIZE")
    with pytest.raises(SystemExit) as stopped:
        load_settings(Settings)
    assert VALUE not in str(stopped.value.code)
    assert "APP_DB_POOL_SIZE" in str(stopped.value.code)


def test_k04_c10_secret_fields_declare_no_default() -> None:
    fields = Settings.model_fields.items()
    secret_fields = {name: field for name, field in fields if field.annotation is SecretStr}
    assert {name.upper() for name in secret_fields} == set(SECRETS)
    for name, field in secret_fields.items():
        assert field.is_required(), name


def test_k03_pool_settings_are_required_so_the_budget_reads_what_containers_receive() -> None:
    for name in ("app_db_pool_size", "app_db_max_overflow"):
        assert Settings.model_fields[name].is_required(), name
