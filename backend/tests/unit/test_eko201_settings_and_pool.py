"""EKO-2-01: the backend's authentication settings and the bounded pool checkout.

- ADR-0004 *Secret handling*, ADR-0004-C10: the OIDC client secret and the session-token key have
  no default, and a missing or empty one stops the component naming only the variable.
- ADR-0003-C2, backend half: configured leeway plus maximum clock offset is at most 60 seconds,
  so that with the realm's `accessTokenLifespan` of 240 the sum stays within 300.
- ADR-0002 addendum of 2026-11-02 (G-6 A), configuration half of ADR-0002-C16: every engine
  `create_app_engine` builds waits at most 0.5 seconds for a pooled connection.
"""

import base64
from typing import Any

import pytest
from pydantic import SecretStr

from app.core import settings as settings_module
from app.core.settings import load_settings

KEY = base64.urlsafe_b64encode(b"s" * 32).decode("ascii")
VALUES = {
    "APP_ORIGIN": "https://app.example.invalid",
    "APP_OIDC_ISSUER": "https://auth.example.invalid/realms/eko",
    "APP_OIDC_CLIENT_SECRET": "synthetic-client-secret-91c2",
    "APP_SESSION_ENCRYPTION_KEY": KEY,
}
SECRETS = ("APP_OIDC_CLIENT_SECRET", "APP_SESSION_ENCRYPTION_KEY")
REALM_ACCESS_TOKEN_LIFESPAN = 240


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in VALUES.items():
        monkeypatch.setenv(name, value)


def auth_settings() -> Any:
    return load_settings(settings_module.AuthSettings)


def test_eko201_auth_settings_load_with_every_required_variable(env: None) -> None:
    loaded = auth_settings()
    assert loaded.app_oidc_client_id == "eko-backend"
    assert loaded.app_oidc_internal_url is None
    assert isinstance(loaded.app_oidc_client_secret, SecretStr)


@pytest.mark.parametrize("name", [*VALUES])
def test_eko201_missing_required_variable_stops_naming_it(
    env: None, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)
    with pytest.raises(SystemExit) as stopped:
        auth_settings()
    assert name in str(stopped.value.code)
    for value in VALUES.values():
        assert value not in str(stopped.value.code)


@pytest.mark.parametrize("name", SECRETS)
@pytest.mark.parametrize("empty", ["", "   "])
def test_eko201_empty_secret_stops_naming_it(
    env: None, monkeypatch: pytest.MonkeyPatch, name: str, empty: str
) -> None:
    monkeypatch.setenv(name, empty)
    with pytest.raises(SystemExit) as stopped:
        auth_settings()
    assert name in str(stopped.value.code)


@pytest.mark.parametrize(
    "key",
    [base64.urlsafe_b64encode(b"s" * 31).decode(), base64.urlsafe_b64encode(b"s" * 33).decode(),
     "not base64 !!"],
    ids=["31-bytes", "33-bytes", "garbage"],
)  # fmt: skip
def test_eko201_session_key_must_be_32_bytes(
    env: None, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv("APP_SESSION_ENCRYPTION_KEY", key)
    with pytest.raises(SystemExit) as stopped:
        auth_settings()
    assert "APP_SESSION_ENCRYPTION_KEY" in str(stopped.value.code)
    assert key not in str(stopped.value.code)


def test_eko201_secret_fields_declare_no_default() -> None:
    fields = settings_module.AuthSettings.model_fields
    for name in ("app_oidc_client_secret", "app_session_encryption_key"):
        assert fields[name].is_required(), name


@pytest.mark.parametrize(
    "origin", ["https://app.example.invalid/", "https://app.example.invalid/path", "app.example"]
)
def test_eko201_origin_must_be_scheme_and_host_only(
    env: None, monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    monkeypatch.setenv("APP_ORIGIN", origin)
    with pytest.raises(SystemExit) as stopped:
        auth_settings()
    assert "APP_ORIGIN" in str(stopped.value.code)


def test_eko201_c2_leeway_plus_offset_fits_the_realm_lifespan(env: None) -> None:
    loaded = auth_settings()
    total = (
        REALM_ACCESS_TOKEN_LIFESPAN
        + loaded.app_oidc_clock_skew_leeway_seconds
        + loaded.app_oidc_max_clock_offset_seconds
    )
    assert total <= 300


@pytest.mark.parametrize(("leeway", "offset"), [("31", "30"), ("0", "61"), ("61", "0")])
def test_eko201_c2_configured_sum_above_60_seconds_stops(
    env: None, monkeypatch: pytest.MonkeyPatch, leeway: str, offset: str
) -> None:
    monkeypatch.setenv("APP_OIDC_CLOCK_SKEW_LEEWAY_SECONDS", leeway)
    monkeypatch.setenv("APP_OIDC_MAX_CLOCK_OFFSET_SECONDS", offset)
    with pytest.raises(SystemExit):
        auth_settings()


def test_eko201_c16_every_application_engine_waits_at_most_half_a_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import Settings
    from app.data.database import create_app_engine

    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-pool-pw")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "5")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "5")
    engine = create_app_engine(load_settings(Settings))
    try:
        assert engine.pool.timeout() == 0.5  # type: ignore[attr-defined]
        assert engine.pool.size() == 5  # type: ignore[attr-defined]
    finally:
        engine.dispose()


def test_eko201_serve_stops_before_spawning_workers_on_a_missing_auth_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    from app import serve

    calls: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(serve, "refuse_unless_servable", lambda settings, process: None)
    for name, value in VALUES.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-serve-pw")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "5")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "5")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.delenv("APP_OIDC_CLIENT_SECRET")
    with pytest.raises(SystemExit) as stopped:
        serve.main()
    assert "APP_OIDC_CLIENT_SECRET" in str(stopped.value.code)
    assert calls == []
