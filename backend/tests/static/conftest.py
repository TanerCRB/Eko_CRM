import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support.repo import REPO_ROOT, read_text, render, tracked_files, write_synthetic_env

COMPOSE = REPO_ROOT / "compose.yaml"
CASES = Path(__file__).parent / "fixtures" / "composition_cases.yaml"
SECRET_NAME = re.compile(r"(PASSWORD|SECRET|KEY|CREDENTIAL|TOKEN)")
# ADR-0004 *Secret handling* rows not yet used by any service; a value for them is a secret too.
FUTURE_SECRETS = {
    "KC_DB_PASSWORD",
    "KC_BOOTSTRAP_ADMIN_PASSWORD",
    "SESSION_ENCRYPTION_KEY",
    "OIDC_CLIENT_SECRET",
    "SMTP_PASSWORD",
    "BACKUP_DESTINATION_CREDENTIAL",
    "PROXY_ADMIN_TLS_KEY",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_TOKEN_ENCRYPTION_KEY",
}

Rendered = dict[str, Any]


@pytest.fixture(scope="session")
def synthetic_env(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_synthetic_env(tmp_path_factory.mktemp("env") / "synthetic.env")


@pytest.fixture(scope="session")
def rendered_dev(synthetic_env: Path) -> Rendered:
    return render(synthetic_env, dev_profile=True)


@pytest.fixture(scope="session")
def rendered_shared(synthetic_env: Path) -> Rendered:
    return render(synthetic_env, dev_profile=False)


@pytest.fixture(scope="session")
def compose_source() -> dict[str, Any]:
    source: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return source


@pytest.fixture(scope="session")
def secret_inventory(compose_source: dict[str, Any]) -> set[str]:
    text = COMPOSE.read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", text))
    return {name for name in required if SECRET_NAME.search(name)} | FUTURE_SECRETS


@pytest.fixture(scope="session")
def repo_files() -> dict[str, str]:
    files = {}
    for path in tracked_files():
        text = read_text(path)
        if text is not None:
            files[path] = text
    return files


def composition_cases() -> list[dict[str, str]]:
    cases: list[dict[str, str]] = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    return cases


def case(case_id: str) -> dict[str, str]:
    for item in composition_cases():
        if item["id"] == case_id:
            return item
    raise KeyError(case_id)


@pytest.fixture
def mutated(tmp_path: Path) -> Callable[[str], Path]:
    """compose.yaml with one fixture case applied, written beside nothing else."""

    def apply(case_id: str) -> Path:
        item = case(case_id)
        text = COMPOSE.read_text(encoding="utf-8")
        assert text.count(item["old"]) == 1, f"{case_id}: 'old' must occur exactly once"
        target = tmp_path / "compose.yaml"
        target.write_text(text.replace(item["old"], item["new"]), encoding="utf-8")
        return target

    return apply


@pytest.fixture
def render_case(
    mutated: Callable[[str], Path], synthetic_env: Path
) -> Callable[[str, bool], Rendered]:
    def apply(case_id: str, dev_profile: bool = False) -> Rendered:
        return render(synthetic_env, dev_profile=dev_profile, compose_file=mutated(case_id))

    return apply


@pytest.fixture
def source_case(mutated: Callable[[str], Path]) -> Callable[[str], dict[str, Any]]:
    def apply(case_id: str) -> dict[str, Any]:
        loaded: dict[str, Any] = yaml.safe_load(mutated(case_id).read_text(encoding="utf-8"))
        return loaded

    return apply
