"""EKO-2-01 R-07: the bootstrap tells an application realm that lacks the export's browser flow
(a realm persisted before EKO-2-01; a partial import cannot add a flow) apart from settings
drift. Absent flow: its own message and exit 8. Drift: the existing message and exit 7. Both
keep the public listener closed. Runs the bootstrap's own functions against a fake Keycloak."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.support.repo import REPO_ROOT

BOOTSTRAP = REPO_ROOT / "scripts" / "keycloak-bootstrap.py"
EXPORT = REPO_ROOT / "identity" / "eko-realm.json"
ORIGIN = "https://app.example.test:8443"


def bootstrap(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("eko_keycloak_bootstrap_pre", BOOTSTRAP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "EXPORT_FILE", EXPORT)
    monkeypatch.setenv("APP_ORIGIN", ORIGIN)
    return module


class FakeKeycloak:
    """Answers the admin GETs the precondition reads, from an in-memory realm."""

    def __init__(self, module: ModuleType, realm: dict[str, Any], flows: list[str]) -> None:
        self.module = module
        self.realm = realm
        self.flows = flows
        self.client = {
            "id": "c1",
            "clientId": "eko-backend",
            "rootUrl": ORIGIN,
            "redirectUris": ["/api/auth/callback"],
            "protocolMappers": [
                {
                    "protocolMapper": "oidc-audience-mapper",
                    "config": {"included.client.audience": "eko-backend"},
                }
            ],
        }
        self.executions = [
            {"providerId": "auth-username-password-form", "requirement": "REQUIRED"},
            {"providerId": "auth-otp-form", "requirement": "REQUIRED"},
        ]

    def request(
        self, method: str, path: str, *, headers: dict[str, str], data: Any, body: Any
    ) -> Any:
        assert method == "GET", path
        if path == "/admin/realms/eko":
            answer: Any = self.realm
        elif path == "/admin/realms/eko/authentication/flows":
            answer = [{"alias": alias} for alias in self.flows]
        elif path.startswith("/admin/realms/eko/authentication/flows/"):
            answer = self.executions
        elif path.startswith("/admin/realms/eko/clients?clientId="):
            answer = [self.client]
        else:
            raise AssertionError(path)
        return self.module.ApiResponse(200, answer, {})


def live_realm(module: ModuleType) -> dict[str, Any]:
    settings: dict[str, Any] = module.export_settings()
    return dict(settings)


def emitted(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [json.loads(line)["event"] for line in capsys.readouterr().out.splitlines() if line]


def test_a_realm_without_the_export_flow_exits_8_with_its_own_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = bootstrap(monkeypatch)
    fake = FakeKeycloak(module, live_realm(module), ["browser", "direct grant"])
    with pytest.raises(SystemExit) as stopped:
        module.require_browser_flow(fake, "token", module.export_settings())
    assert stopped.value.code == 8
    assert emitted(capsys) == ["application browser flow absent"]


def test_contrast_the_same_realm_with_the_flow_passes_the_flow_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = bootstrap(monkeypatch)
    fake = FakeKeycloak(module, live_realm(module), ["browser", "eko browser", "eko browser forms"])
    module.require_browser_flow(fake, "token", module.export_settings())
    assert emitted(capsys) == []


def test_settings_drift_keeps_exit_7_and_the_drift_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = bootstrap(monkeypatch)
    realm = live_realm(module)
    realm["failureFactor"] = 30
    fake = FakeKeycloak(module, realm, ["eko browser"])
    with pytest.raises(SystemExit) as stopped:
        module.verify_application_settings(fake, "token", module.export_settings())
    assert stopped.value.code == 7
    assert emitted(capsys) == ["application security settings not applied"]


def test_contrast_no_drift_is_verified(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = bootstrap(monkeypatch)
    fake = FakeKeycloak(module, live_realm(module), ["eko browser"])
    module.verify_application_settings(fake, "token", module.export_settings())
    assert emitted(capsys) == ["application security settings verified"]


def test_the_two_exit_codes_and_messages_differ() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert text.count('emit("application browser flow absent")') == 1
    assert text.count("raise SystemExit(8)") == 1
    assert (
        Path(BOOTSTRAP)
        .read_text(encoding="utf-8")
        .count('emit("application security settings not applied")')
        == 1
    )
