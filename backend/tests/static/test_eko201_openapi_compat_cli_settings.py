"""EKO-2-01: the API-compatibility command builds the application without the pytest conftest.

CI runs `python -m tests.support.openapi_compat` after pytest (`.github/workflows/ci.yml`, and
`release.yml` with `--exclude`); that process never loads `tests/conftest.py`, so the synthetic
settings `create_app()` requires must come from `api_surface.synthetic_settings()` itself.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import api_surface as api
from tests.support.synthetic_auth import SYNTHETIC_AUTH_SETTINGS

BACKEND = Path(__file__).resolve().parents[2]


def environment_without_app_settings() -> dict[str, str]:
    """The caller's environment minus every `APP_*` setting: what conftest would have masked."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("APP_")}


def test_eko201_openapi_compat_cli_runs_without_app_settings(tmp_path: Path) -> None:
    previous = tmp_path / "head.json"
    previous.write_text(json.dumps(api.real_app().openapi()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "tests.support.openapi_compat", "--previous", str(previous)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=environment_without_app_settings(),
        timeout=120,
    )
    output = result.stdout + result.stderr
    assert "configuration error" not in output, output
    assert result.returncode == 0, output
    assert "no breaking change" in result.stdout, output


def test_eko201_synthetic_settings_yield_to_the_caller_and_are_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in SYNTHETIC_AUTH_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ORIGIN", "https://caller-chosen.invalid")
    with api.synthetic_settings():
        assert os.environ["APP_ORIGIN"] == "https://caller-chosen.invalid"
        assert os.environ["APP_OIDC_ISSUER"] == SYNTHETIC_AUTH_SETTINGS["APP_OIDC_ISSUER"]
    assert os.environ["APP_ORIGIN"] == "https://caller-chosen.invalid"
    assert "APP_OIDC_ISSUER" not in os.environ
