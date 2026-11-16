"""EKO-2-01 F-1 A, bootstrap half: the client root URL Keycloak redirects to is the application
origin exactly as the backend uses it, a default port (443 https, 80 http) dropped and any other
port kept (`app.core.settings.without_default_port`). The bootstrap sets the root URL from that
form, and its live precondition compares that form too."""

import importlib.util
from types import ModuleType

import pytest

from app.core.settings import without_default_port
from tests.support.repo import REPO_ROOT

BOOTSTRAP = REPO_ROOT / "scripts" / "keycloak-bootstrap.py"


def bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location("eko_keycloak_bootstrap", BOOTSTRAP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CASES = [
    ("https://app.example.test:443", "https://app.example.test"),
    ("http://app.example.test:80", "http://app.example.test"),
    ("https://app.example.test:8443", "https://app.example.test:8443"),
    ("https://localhost:51234", "https://localhost:51234"),
    ("https://app.example.test", "https://app.example.test"),
    ("http://app.example.test:443", "http://app.example.test:443"),
    ("https://app.example.test:80", "https://app.example.test:80"),
    ("https://[::1]:443", "https://[::1]"),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_bootstrap_origin_drops_only_a_default_port(
    raw: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ORIGIN", raw)
    assert bootstrap().application_origin() == expected


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_bootstrap_and_backend_normalise_identically(raw: str, expected: str) -> None:
    assert without_default_port(raw) == expected


def test_contrast_the_raw_443_origin_is_not_what_the_backend_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = "https://app.example.test:443"
    monkeypatch.setenv("APP_ORIGIN", raw)
    assert bootstrap().application_origin() != raw


def test_root_url_and_precondition_both_use_the_normalised_origin() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'application["rootUrl"] = application_origin()' in text
    assert 'application.get("rootUrl") != application_origin()' in text
    assert (
        'required("APP_ORIGIN")' in text.split("def application_origin", 1)[1].split("\ndef ", 1)[0]
    )
    assert text.count('required("APP_ORIGIN")') == 1
