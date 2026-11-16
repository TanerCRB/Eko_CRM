"""EKO-2-01, human decision F-1 A (#21): the default port is removed from `APP_ORIGIN` and
`APP_OIDC_ISSUER` at load time.

Keycloak writes `iss` without an explicit default port, and a browser sends `Origin` without
one, while the composition derives both settings as `https://<host>:<PROXY_HTTPS_PORT>`. Each
contrast puts the un-normalised value back on the running object and shows it refused.
"""

import time
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth.oidc import OidcClient, TokenInvalid
from app.core.settings import AuthSettings, load_settings
from app.main import create_app
from tests.support import oidc_stub

KEY = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("APP_ORIGIN", "https://app.example.invalid")
    monkeypatch.setenv("APP_OIDC_ISSUER", "https://auth.example.invalid/realms/eko")
    monkeypatch.setenv("APP_OIDC_CLIENT_SECRET", "synthetic-f1-secret")
    monkeypatch.setenv("APP_SESSION_ENCRYPTION_KEY", KEY)
    return monkeypatch


@pytest.mark.parametrize(
    ("given", "loaded"),
    [
        ("https://app.example.invalid:443", "https://app.example.invalid"),
        ("http://app.example.invalid:80", "http://app.example.invalid"),
        ("https://app.example.invalid:8443", "https://app.example.invalid:8443"),
        ("https://app.example.invalid:80", "https://app.example.invalid:80"),
        ("http://app.example.invalid:443", "http://app.example.invalid:443"),
        ("https://[::1]:443", "https://[::1]"),
        ("https://app.example.invalid", "https://app.example.invalid"),
    ],
)
def test_eko201_f1_origin_loses_only_its_default_port(
    auth_env: pytest.MonkeyPatch, given: str, loaded: str
) -> None:
    auth_env.setenv("APP_ORIGIN", given)
    assert load_settings(AuthSettings).app_origin == loaded


@pytest.mark.parametrize(
    ("given", "loaded"),
    [
        ("https://auth.example.invalid:443/realms/eko", "https://auth.example.invalid/realms/eko"),
        ("http://auth.example.invalid:80/realms/eko", "http://auth.example.invalid/realms/eko"),
        (
            "https://auth.example.invalid:8443/realms/eko",
            "https://auth.example.invalid:8443/realms/eko",
        ),
    ],
)
def test_eko201_f1_issuer_loses_only_its_default_port(
    auth_env: pytest.MonkeyPatch, given: str, loaded: str
) -> None:
    auth_env.setenv("APP_OIDC_ISSUER", given)
    assert load_settings(AuthSettings).app_oidc_issuer == loaded


def test_eko201_f1_origin_with_a_path_is_still_refused(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("APP_ORIGIN", "https://app.example.invalid:443/")
    with pytest.raises(SystemExit) as stopped:
        load_settings(AuthSettings)
    assert "APP_ORIGIN" in str(stopped.value.code)


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _signed_access(issuer: str, key: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer, "sub": "4b1c2d3e-0000-4000-8000-0000000000f1", "aud": ["eko-backend"],
        "azp": "eko-backend", "typ": "Bearer", "iat": now, "exp": now + 240,
    }  # fmt: skip
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "f1"})


def test_eko201_f1_token_with_the_port_less_issuer_is_accepted(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("APP_OIDC_ISSUER", "https://auth.example.invalid:443/realms/eko")
    settings = load_settings(AuthSettings)
    key = oidc_stub.new_key()
    keys = {"keys": [oidc_stub.public_jwk(key, "f1")]}
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=keys)))
    client = OidcClient(settings, http)
    # As Keycloak writes it: no explicit default port.
    token = _signed_access("https://auth.example.invalid/realms/eko", key)
    assert client.verify_access(token, _Clock()).subject.endswith("f1")
    # Contrast: the value as the composition derives it, not normalised, refuses the same token.
    client.issuer = "https://auth.example.invalid:443/realms/eko"
    with pytest.raises(TokenInvalid):
        client.verify_access(token, _Clock())


def test_eko201_f1_origin_header_without_443_passes_the_origin_check(
    backend_env: None, auth_env: pytest.MonkeyPatch
) -> None:
    auth_env.setenv("APP_ORIGIN", "https://app.example.invalid:443")
    app = create_app()
    with TestClient(app) as client:
        # Past the origin check: no session, so 401, not the origin refusal's 403.
        answer = client.post("/api/auth/logout", headers={"origin": "https://app.example.invalid"})
        assert answer.status_code == 401, answer.text
        # Contrast: the un-normalised origin refuses the header a browser actually sends.
        app.state.auth.origin = "https://app.example.invalid:443"
        refused = client.post("/api/auth/logout", headers={"origin": "https://app.example.invalid"})
        assert refused.status_code == 403, refused.text
