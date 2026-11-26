"""EKO-3-06, composition half of ADR-0005-C22 and ADR-0004-C37 (A-3 A): the synthetic-only
declaration is one non-secret environment variable of `worker`, never declared by default.

- The composition source wires `APP_SYNTHETIC_DATA_ONLY` on `worker` only, as an interpolation
  of the environment's own variable with an empty default (unset means "not declared"); no other
  service names it.
- Both rendered profiles, from the generated synthetic environment file, hand `worker` an empty
  value: the shipped composition and `scripts/dev-env.sh` never declare an environment.
- The same rendering with the accepted value in the environment file hands `worker` exactly that
  value, and any other value unchanged: Compose carries the value, the backend judges it.
- The release composition keeps the line as written: a release declares no environment either.
- `docker compose config --services` is unchanged by this task (ADR-0004-C37).

What the backend accepts, and that it reads the variable only in `settings.py`, is the backend
half of ADR-0005-C22 (developer-backend), not proven here.
"""

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.conftest import COMPOSE
from tests.support import compose_checks as cc
from tests.support import release_composition as rc
from tests.support.repo import REPO_ROOT, compose_env, render, write_synthetic_env

VARIABLE = "APP_SYNTHETIC_DATA_ONLY"
# The one exact value the backend accepts (ADR-0005 addendum, EKO-3-06). Not a secret.
ACCEPTED = "declared"
WIRING = "${" + VARIABLE + ":-}"
# The service list before EKO-3-06 (ADR-0004-C1 with the 2026-10-27 worker addendum).
SERVICES_BEFORE = {
    "dev": sorted(cc.DEV_SERVICES),
    "shared": sorted(cc.SHARED_SERVICES),
}


def _environment(service: dict[str, Any]) -> dict[str, Any]:
    environment = service.get("environment") or {}
    if isinstance(environment, list):
        pairs = (item.split("=", 1) if "=" in item else (item, None) for item in environment)
        return {key: value for key, value in pairs}
    assert isinstance(environment, dict)
    return environment


def _naming_services(services: dict[str, dict[str, Any]]) -> list[str]:
    """Services whose environment names the variable, as a key or inside a value."""
    found = []
    for name, service in services.items():
        for key, value in _environment(service).items():
            if VARIABLE in key or VARIABLE in str(value or ""):
                found.append(name)
                break
    return sorted(found)


def _with_line(env_file: Path, target: Path, line: str) -> Path:
    target.write_text(env_file.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    return target


@pytest.fixture
def clean_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """A value in the caller's shell would win over the environment file; the checks read the
    composition and the file only."""
    monkeypatch.delenv(VARIABLE, raising=False)


# The source -------------------------------------------------------------------------------------


def test_eko306_c22_worker_wires_the_declaration_from_the_environment(
    compose_source: dict[str, Any],
) -> None:
    worker = _environment(compose_source["services"]["worker"])
    assert worker.get(VARIABLE) == WIRING


def test_eko306_c22_no_other_service_names_the_declaration(
    compose_source: dict[str, Any],
) -> None:
    assert _naming_services(compose_source["services"]) == ["worker"]


def test_eko306_c22_the_declaration_is_not_in_the_secret_inventory(
    secret_inventory: set[str],
) -> None:
    # Not a secret (ADR-0005 addendum): it is neither required with no default nor named like one.
    assert VARIABLE not in secret_inventory
    assert VARIABLE not in set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", COMPOSE.read_text("utf-8")))


# The rendering ----------------------------------------------------------------------------------


@pytest.mark.parametrize("dev_profile", [True, False], ids=["dev", "shared"])
def test_eko306_c22_rendered_worker_is_not_declared_by_default(
    synthetic_env: Path, clean_shell: None, dev_profile: bool
) -> None:
    assert VARIABLE not in synthetic_env.read_text(encoding="utf-8")
    services = render(synthetic_env, dev_profile=dev_profile)["services"]
    assert services["worker"]["environment"][VARIABLE] == ""
    assert _naming_services(services) == ["worker"]


@pytest.mark.parametrize("value", [ACCEPTED, "false", "Declared", " declared"])
@pytest.mark.parametrize("dev_profile", [True, False], ids=["dev", "shared"])
def test_eko306_c22_an_environment_file_line_reaches_worker_unchanged(
    synthetic_env: Path, clean_shell: None, tmp_path: Path, dev_profile: bool, value: str
) -> None:
    """How a developer, test or (after the C16 statement) shared environment declares itself:
    one line in its own untracked environment file. Compose passes the value as written."""
    quoted = f'"{value}"' if value != value.strip() else value
    env_file = _with_line(synthetic_env, tmp_path / "declared.env", f"{VARIABLE}={quoted}")
    services = render(env_file, dev_profile=dev_profile)["services"]
    assert services["worker"]["environment"][VARIABLE] == value
    assert _naming_services(services) == ["worker"]


def test_eko306_c22_release_composition_keeps_the_declaration_unset() -> None:
    digests = {
        name: "sha256:" + (name.encode().hex() * 64)[:64]
        for name in (*rc.PROJECT_IMAGES, "postgres")
    }
    release: dict[str, Any] = yaml.safe_load(
        rc.render(COMPOSE.read_text(encoding="utf-8"), "v1.2.0", digests)
    )
    assert _environment(release["services"]["worker"]).get(VARIABLE) == WIRING
    assert _naming_services(release["services"]) == ["worker"]


# ADR-0004-C37: the service list -----------------------------------------------------------------


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_eko306_c37_compose_config_services_is_unchanged(synthetic_env: Path, profile: str) -> None:
    args = ["docker", "compose", "--env-file", str(synthetic_env)]
    if profile == "dev":
        args += ["--profile", "dev"]
    listed = subprocess.run(
        [*args, "config", "--services"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=compose_env(),
    ).stdout.split()
    assert sorted(listed) == SERVICES_BEFORE[profile]


def test_eko306_c22_a_generated_environment_file_never_declares(tmp_path: Path) -> None:
    """`scripts/dev-env.sh` writes only required variables: a developer declares by adding the
    line, which is the developer's own statement (ADR-0005 addendum)."""
    env_file = write_synthetic_env(tmp_path / "fresh.env")
    assert VARIABLE not in env_file.read_text(encoding="utf-8")
