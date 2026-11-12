"""EKO-1-12 K-06: closed synthetic fixtures and secret-free versioned realm files.

EKO-1-29 (K-01a..K-03): the tracked-additions secret scan gained raw-format teeth — the scan
predicate is extracted into `find_literal_secret_assignment_lines` and guarded in-file by
committed in-memory plants: raw keyword-terminated `NAME=literal` shapes fire under each of the
four scanned prefixes, diff-form `+NAME=literal` teeth survive, and placeholder, path-valued and
self-reference shapes (the current-main `TOKEN_FILE=/etc/...` and `token=token,` pair) hold.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.support import eko112_fixtures as fixtures
from tests.support.repo import REPO_ROOT, read_text, tracked_files

ENV_PLACEHOLDER = re.compile(r"^\$\{[A-Z][A-Z0-9_]*\}$")
# EKO-1-29 (exception EKO-1-12/Q3-1): the old SECRET_ENV_ASSIGNMENT anchored on `^\+`, so a
# raw `SOME_KEY=literal` passed a scan that reads file content, and `POSTGRES_PASSWORD=` passed
# the word boundary before the keyword. The predicate is now the union of the raw assignment
# shape and the retained diff-form shape; the keyword set is unchanged (Story: out of scope).
_KEYWORD_TERMINATED_NAME = r"[A-Za-z0-9_]*?(?:PASSWORD|SECRET|TOKEN|CREDENTIAL|KEY)"
_QUOTED_LITERAL = r'"[^$\s][^"]*"' r"|'[^$\s][^']*'"
# A bare value excludes `$`-references and quotes; the self-reference passing is held in
# `_is_literal_value` instead — Python's `re` has no non-consuming named backreference.
_BARE_LITERAL = r"[^$\s\"'][^\s]*"
_LITERAL_VALUE = rf"(?P<value>{_QUOTED_LITERAL}|{_BARE_LITERAL})"
RAW_SECRET_ASSIGNMENT = re.compile(
    rf"^\s*(?:export\s+)?(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}", re.IGNORECASE
)
DIFF_SECRET_ASSIGNMENT = re.compile(
    rf"^\+[^+].*(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}", re.IGNORECASE
)
_STATEMENT_TAIL = ",;:)]}"
SECRET_SCAN_PREFIXES = ("identity/", "proxy/", "docs/evidence/EKO-1-12/", "scripts/keycloak-")


def _is_literal_value(name: str, value: str) -> bool:
    if value[0] in "\"'":
        return True
    # `token=token,` passes a variable, not a literal (the kwarg lines that keep the merged
    # suite green at rest in scripts/keycloak-bootstrap.py); a quoted value is deliberate.
    return value.rstrip(_STATEMENT_TAIL).casefold() != name.casefold()


def is_secret_env_assignment(line: str) -> bool:
    for pattern in (RAW_SECRET_ASSIGNMENT, DIFF_SECRET_ASSIGNMENT):
        match = pattern.match(line)
        if match is not None and _is_literal_value(match["name"], match["value"]):
            return True
    return False


def find_literal_secret_assignment_lines(relative: str, text: str) -> list[int]:
    """The scan predicate: 1-based line numbers of literal secret environment assignments."""
    if not relative.startswith(SECRET_SCAN_PREFIXES):
        return []
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if is_secret_env_assignment(line)
    ]


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
    # G-22 (guardian re-verification round 2): the scan follows the complete tracked change
    # set of this task, which includes the runtime files added under `proxy/` (entrypoint,
    # boot-identity helper) — a literal secret assignment there must fail this check too.
    # EKO-1-29 (Q3-1): the predicate now fires on the raw NAME=literal shapes as well.
    for relative in tracked_files():
        text = read_text(relative)
        if text is None:
            continue
        flagged = find_literal_secret_assignment_lines(relative, text)
        assert not flagged, f"{relative}: line(s) {flagged}: literal secret environment assignment"


# --- EKO-1-29 K-01a..K-03: permanent in-file contrast guard of the scan predicate. The plants
# are in-memory text presented as if read from a scanned path; the live scan above runs on the
# tracked tree. Synthetic values only — no real secret appears in any of these strings.

SCANNED_PATHS_UNDER_TEST = [
    "identity/eko-realm.json",
    "proxy/entrypoint.sh",
    "docs/evidence/EKO-1-12/bootstrap.md",
    "scripts/keycloak-bootstrap.sh",
]
# Near misses of the same four prefixes: the prefix filter stays real (K-02 contrast).
UNSCANNED_PATHS_UNDER_TEST = [
    "backend/app/secret-runner.sh",
    "docs/evidence/EKO-1-13/notes.md",
    "scripts/dev-env.sh",
    "identities/entrypoint.sh",
]
RAW_FIRE_SHAPES = [
    "SOME_KEY=literal",
    'SOME_KEY="literal"',
    "SOME_KEY='literal'",
    "ADMIN_API_KEY=admin-plaintext-1",
    "CLIENT_SECRET=client-plaintext-1",
    "ADMIN_POSTGRES_PASSWORD=postgres-plaintext",
    "export TEST_SECRET=exported-plaintext",
    "\tPASSWORD=tab-indented-plain",
    "    TOKEN=space-indented-plain",
    "client_key=lower-case-plain",
    "CREDENTIAL=heslö-plaintext",
]
DIFF_FIRE_SHAPES = [
    "+SOME_KEY=literal",
    "+POSTGRES_PASSWORD=x",
    '+ADMIN_SECRET="lit-eral"',
    "+\texport CLIENT_SECRET='lit-eral'",
]
# K-01 contrast plus the at-rest shapes the merged suite's green depends on: placeholders, a
# path-valued name that merely contains a keyword, and Python's self-reference kwarg passings.
HOLD_SHAPES = [
    "KEY=${VAR}",
    'KEY="${VAR}"',
    "KEY='${VAR}'",
    "TOKEN_FILE=/etc/eko/keycloak-boot/token",
    '    token="$identity"',
    '    token="${token#*-}"',
    "        token=token,",
]
DIFF_HOLD_SHAPES = [
    "+normal-shell-line",
    "+KEY=${VAR}",
    "+++ b/proxy/entrypoint.sh",
    "+  TOKEN_FILE=/etc/eko/keycloak-boot/token",
]


@pytest.mark.parametrize("shape", RAW_FIRE_SHAPES)
def test_eko129_k01a_raw_keyword_terminated_assignment_shapes_fire(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == [1]


@pytest.mark.parametrize("shape", RAW_FIRE_SHAPES)
@pytest.mark.parametrize("path", SCANNED_PATHS_UNDER_TEST)
def test_eko129_k02_the_same_raw_shapes_fire_under_every_scanned_prefix(
    path: str, shape: str
) -> None:
    assert find_literal_secret_assignment_lines(path, shape) == [1]


@pytest.mark.parametrize("shape", RAW_FIRE_SHAPES)
@pytest.mark.parametrize("path", UNSCANNED_PATHS_UNDER_TEST)
def test_eko129_k02_contrast_raw_shapes_outside_the_scanned_prefixes_do_not_fire(
    path: str, shape: str
) -> None:
    assert find_literal_secret_assignment_lines(path, shape) == []


@pytest.mark.parametrize("shape", HOLD_SHAPES)
def test_eko129_k01_contrast_placeholder_path_and_self_reference_shapes_hold(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/keycloak-boot-identity.sh", shape) == []


@pytest.mark.parametrize("shape", DIFF_FIRE_SHAPES)
def test_eko129_k03_diff_form_lines_still_fire(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == [1]


@pytest.mark.parametrize("shape", DIFF_HOLD_SHAPES)
def test_eko129_k03_contrast_diff_form_non_assignments_and_placeholders_hold(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == []


def test_eko129_k01a_edge_two_identical_raw_assignments_are_two_reported_lines() -> None:
    text = "SOME_KEY=literal\nset -eu\nSOME_KEY=literal\n"
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", text) == [1, 3]


def test_eko129_k01a_edge_raw_assignments_on_the_first_and_the_last_line_are_flagged() -> None:
    text = "export TOKEN=first-line-plain\necho middle\nADMIN_API_KEY=last-line-plain"
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", text) == [1, 3]


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
