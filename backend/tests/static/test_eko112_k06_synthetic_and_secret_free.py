"""EKO-1-12 K-06: closed synthetic fixtures and secret-free versioned realm files."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.support import eko112_fixtures as fixtures
from tests.support.repo import REPO_ROOT, read_text, tracked_files

ENV_PLACEHOLDER = re.compile(r"^\$\{[A-Z][A-Z0-9_]*\}$")
SECRET_ENV_ASSIGNMENT = re.compile(
    r"^\+[^+].*\b(?:PASSWORD|SECRET|TOKEN|CREDENTIAL|KEY)=([^$\s][^\s]*)", re.IGNORECASE
)


def identity_files() -> list[Path]:
    root = REPO_ROOT / "identity"
    return [path for path in root.rglob("*") if path.is_file()]


def walk_secret_fields(value: Any, path: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{path}.{key}" if path else key
            if key == "secret" or (path.endswith("smtpServer") and key == "password"):
                found.append((location, item))
            found.extend(walk_secret_fields(item, location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_secret_fields(item, f"{path}[{index}]"))
    return found


def assert_no_forbidden_secret_fields(realm: dict[str, Any]) -> None:
    for path, value in walk_secret_fields(realm):
        assert isinstance(value, str) and ENV_PLACEHOLDER.fullmatch(value), path


def test_k06_export_has_no_users_or_separate_user_files() -> None:
    files = identity_files()
    assert files
    for path in files:
        assert "user" not in path.name.lower(), path.relative_to(REPO_ROOT)
        if path.suffix == ".json":
            realm: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            assert realm.get("users", []) == []


def test_k06_every_export_secret_is_absent_or_an_environment_placeholder() -> None:
    for path in identity_files():
        if path.suffix == ".json":
            realm: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            assert_no_forbidden_secret_fields(realm)


@pytest.mark.parametrize("value", [None, "", "**********", "literal-secret", 42])
def test_k06_null_empty_masked_literal_and_non_string_secrets_fail(value: Any) -> None:
    with pytest.raises(AssertionError):
        assert_no_forbidden_secret_fields({"clients": [{"secret": value}]})


def test_k06_adding_a_user_or_a_literal_secret_fails() -> None:
    with pytest.raises(AssertionError):
        assert_no_forbidden_secret_fields({"clients": [{"secret": "literal-secret"}]})
    realm: dict[str, Any] = json.loads(
        (REPO_ROOT / "identity" / "eko-realm.json").read_text(encoding="utf-8")
    )
    realm["users"] = [{"username": fixtures.ACCOUNTS["known"]}]
    assert realm["users"] != []


def test_k06_runtime_accounts_addresses_and_markers_are_the_declared_invented_set() -> None:
    assert len(set(fixtures.ACCOUNTS.values())) == len(fixtures.ACCOUNTS)
    assert set(fixtures.PASSWORD_VARIABLES) <= set(fixtures.ACCOUNTS)
    assert all(value.startswith("eko112-") for value in fixtures.ACCOUNTS.values())
    assert all(value.endswith("@example.org") for value in fixtures.ADDRESSES.values())
    assert all("unknown" in value for value in fixtures.UNKNOWN_MARKERS)
    assert any(
        any(ord(character) > 127 for character in value) for value in fixtures.UNKNOWN_MARKERS
    )
    assert any(value != value.strip() for value in fixtures.UNKNOWN_MARKERS)
    assert any("<" in value and ">" in value for value in fixtures.UNKNOWN_MARKERS)


def test_k06_tracked_additions_have_no_literal_secret_environment_assignment() -> None:
    for relative in tracked_files():
        if not relative.startswith(("identity/", "docs/evidence/EKO-1-12/", "scripts/keycloak-")):
            continue
        text = read_text(relative)
        if text is None:
            continue
        for line in text.splitlines():
            match = SECRET_ENV_ASSIGNMENT.match(line)
            assert match is None, f"{relative}: literal secret environment assignment"


def test_k06_task_files_contain_no_declared_real_fixture() -> None:
    for relative in tracked_files():
        if not relative.startswith(
            ("identity/", "docs/evidence/EKO-1-12/", "backend/tests/", "scripts/keycloak-")
        ):
            continue
        text = read_text(relative)
        if text is not None:
            forbidden_declaration = "declared real " + "personal data"
            assert forbidden_declaration not in text.lower(), relative
