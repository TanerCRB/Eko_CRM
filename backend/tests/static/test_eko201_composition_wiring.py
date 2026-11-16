"""EKO-2-01: the backend's authentication settings come from the composition, and only it gets
them (ADR-0003 *Browser flow*, ADR-0004 *Secret handling*; developer-backend hand-back,
"Settings (backend container)").

Both rendered profiles: the five settings are wired from the environment, the issuer is the one
Keycloak writes (its public hostname), the back-channel base stays inside the network, the two
secrets are required interpolations of the declared secret names, and `worker`, `migrate` and
every other service receive none of them. The rendered values satisfy the backend's own
settings validation. `scripts/dev-env.sh` generates a usable session key.
"""

import base64
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.support.repo import REPO_ROOT, bash, render, write_synthetic_env

AUTH_SETTINGS = (
    "APP_ORIGIN",
    "APP_OIDC_ISSUER",
    "APP_OIDC_INTERNAL_URL",
    "APP_OIDC_CLIENT_SECRET",
    "APP_SESSION_ENCRYPTION_KEY",
)
URLSAFE_32 = re.compile(r"[A-Za-z0-9_-]{43}=?")


def env_values(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


@pytest.fixture(params=["dev", "shared"])
def rendered(request: pytest.FixtureRequest, synthetic_env: Path) -> dict[str, Any]:
    result: dict[str, Any] = render(synthetic_env, dev_profile=request.param == "dev")
    return result


def test_backend_receives_the_five_authentication_settings(
    rendered: dict[str, Any], synthetic_env: Path
) -> None:
    env = env_values(synthetic_env)
    backend = rendered["services"]["backend"]["environment"]
    keycloak = rendered["services"]["keycloak"]["environment"]
    assert backend["APP_ORIGIN"] == f"https://{env['APP_HOST']}:{env['PROXY_HTTPS_PORT']}"
    # The issuer Keycloak writes into `iss` is its configured public hostname plus the realm
    # path, for browser and back-channel token calls alike.
    assert backend["APP_OIDC_ISSUER"] == f"{keycloak['KC_HOSTNAME']}/realms/eko"
    assert backend["APP_OIDC_INTERNAL_URL"] == "http://keycloak:8080/realms/eko"
    assert backend["APP_OIDC_CLIENT_SECRET"] == env["OIDC_CLIENT_SECRET"]
    assert backend["APP_OIDC_CLIENT_SECRET"] == keycloak["OIDC_CLIENT_SECRET"]
    assert backend["APP_SESSION_ENCRYPTION_KEY"] == env["SESSION_ENCRYPTION_KEY"]


def test_only_the_backend_receives_them(rendered: dict[str, Any]) -> None:
    leaked = {
        name: sorted(set(service.get("environment") or {}) & set(AUTH_SETTINGS))
        for name, service in rendered["services"].items()
        if name != "backend"
    }
    assert {name: found for name, found in leaked.items() if found} == {}
    for name in ("worker", "migrate"):
        values = " ".join(
            str(value) for value in (rendered["services"][name].get("environment") or {}).values()
        )
        assert "SESSION_ENCRYPTION" not in values and "OIDC" not in values


SECRET_WIRING = {
    "APP_OIDC_CLIENT_SECRET": "OIDC_CLIENT_SECRET",
    "APP_SESSION_ENCRYPTION_KEY": "SESSION_ENCRYPTION_KEY",
}


def test_the_two_secrets_are_required_interpolations_without_default(
    compose_source: dict[str, Any], secret_inventory: set[str]
) -> None:
    """A required reference with no default: `${NAME?message}` (A-01: the colon-less form,
    because the repository's ADR-0004-C9 scan reads `${NAME:` under another key as an
    assignment); an empty value is refused by the backend itself, below."""
    backend = compose_source["services"]["backend"]["environment"]
    for key, name in SECRET_WIRING.items():
        assert name in secret_inventory
        assert re.fullmatch(re.escape("${" + name) + r":?\?[^}]+\}", backend[key]), key
        assert ":-" not in backend[key] and "-" + "}" not in backend[key]


@pytest.mark.parametrize("key", sorted(SECRET_WIRING))
def test_an_empty_secret_is_refused_by_the_backends_settings_naming_it(
    rendered: dict[str, Any], monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    from app.core.settings import AuthSettings, load_settings

    for name, value in rendered["services"]["backend"]["environment"].items():
        monkeypatch.setenv(name, str(value))
    monkeypatch.setenv(key, "")
    with pytest.raises(SystemExit) as refused:
        load_settings(AuthSettings)
    assert key in str(refused.value)


def test_rendered_values_pass_the_backends_own_settings_validation(
    rendered: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.settings import AuthSettings

    for name in AUTH_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    for name, value in rendered["services"]["backend"]["environment"].items():
        monkeypatch.setenv(name, str(value))
    settings = AuthSettings()
    assert len(settings.session_key()) == 32
    assert settings.app_oidc_internal_url == "http://keycloak:8080/realms/eko"


def without(path: Path, name: str, target: Path) -> Path:
    lines = path.read_text(encoding="utf-8").splitlines()
    target.write_text(
        "".join(f"{line}\n" for line in lines if not line.startswith(f"{name}=")), encoding="utf-8"
    )
    return target


@pytest.mark.parametrize("name", ["SESSION_ENCRYPTION_KEY", "OIDC_CLIENT_SECRET"])
def test_rendering_without_either_secret_is_refused_naming_it(
    synthetic_env: Path, tmp_path: Path, name: str
) -> None:
    env_file = without(synthetic_env, name, tmp_path / "missing.env")
    with pytest.raises(subprocess.CalledProcessError) as refused:
        render(env_file, dev_profile=False)
    assert name in (refused.value.stderr or "")


def test_dev_env_generates_a_fresh_url_safe_32_byte_session_key(tmp_path: Path) -> None:
    keys = []
    for label in ("one", "two"):
        values = env_values(write_synthetic_env(tmp_path / f"{label}.env"))
        key = values["SESSION_ENCRYPTION_KEY"]
        assert URLSAFE_32.fullmatch(key), "not url-safe base64 of 32 bytes"
        raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
        assert len(raw) == 32
        keys.append(key)
    assert keys[0] != keys[1]


def test_dev_env_self_test_passes() -> None:
    result = subprocess.run(
        [bash(), "scripts/dev-env.sh", "--self-test"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "session key" in result.stdout
