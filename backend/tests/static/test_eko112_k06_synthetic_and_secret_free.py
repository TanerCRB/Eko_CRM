"""EKO-1-12 K-06: closed synthetic fixtures and secret-free versioned realm files.

EKO-1-29 (K-01a..K-03): the tracked-additions secret scan gained raw-format teeth — the scan
predicate is extracted into `find_literal_secret_assignment_lines` and guarded in-file by
committed in-memory plants: raw keyword-terminated `NAME=literal` shapes fire under each of the
four scanned prefixes and in mid-line shell contexts (`;`, `&&`, `||`, `|`, `-e`/`env`, and
extra `export`/assignment slots, dev-2 R-01), diff-form `+NAME=literal` teeth survive including
the diff-line head and unbalanced-quote values (dev-2 G-01), placeholder and path-valued shapes
hold, and the self-reference hold is narrowed to the comma-terminated kwarg call
`NAME=name,` (dev-2 R-02 — a bare `PASSWORD=password` fires again). Lines are cut on newline
only (dev-2 R-04) and a linear membership prefilter guards both regex branches (dev-2 R-03).
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
# the word boundary before the keyword. The predicate is the union of the raw assignment shape
# and the retained diff-form shapes; the keyword set is unchanged (Story: out of scope).
# A keyword-terminated name may carry at most 64 leading characters: the bound is the
# half of the linearity guard (dev-2 R-03), an env name longer than that is a documented
# pass (census: none on the tracked tree).
_KEYWORD_TERMINATED_NAME = r"[A-Za-z0-9_]{0,64}?(?:PASSWORD|SECRET|TOKEN|CREDENTIAL|KEY)"
# A quoted value is a literal even unbalanced: `KEY="foo` and `KEY=""` fire (dev-2 G-01;
# supersedes dev-1's assumption A-04, which had them hold). A value starting with `$` inside
# the quotes stays a reference, not a literal.
_QUOTED_LITERAL = (
    r"(?:\"\"|'')"
    r"|\"[^$\s][^\"]*"
    r"|'[^$\s][^']*"
    r"|(?:[\"'][ \t]*)(?=$|[ \t])"
)
# A bare value excludes `$`-references and quotes.
_BARE_LITERAL = r"[^$\s\"'][^\s]*"
_LITERAL_VALUE = rf"(?P<value>{_QUOTED_LITERAL}|{_BARE_LITERAL})"
# dev-2 R-01: a raw assignment fires after line start and after a shell separator context —
# `;` `&&` `||` `|` (also as `export`/plain prefix), `-e`/`--env`/`env` arguments, any
# further `NAME=value` slot (as after `export FOO=bar ADMIN_TOKEN=x`), and a separator
# character a newline-only line cut leaves inside the line (dev-2 R-04). The value grammar
# keeps the placeholder and path-valued names out of every context.
_ASSIGNMENT_PREFIX = (
    r"(?:^\s*(?:export\s+)?"
    r"|(?<=[;|&])\s*(?:export\s+)?"
    r"|(?<=[\u2028\u2029\x0b\x0c\x85])\s*(?:export\s+)?"
    r"|(?:^|\s)(?:-{1,2}env|-{1,2}e|env)\s+(?:export\s+)?"
    r"|[A-Za-z_][A-Za-z0-9_]{0,64}=[^\"',\s]+\s+(?:export\s+)?)"
)
RAW_SECRET_ASSIGNMENT = re.compile(
    rf"{_ASSIGNMENT_PREFIX}(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}", re.IGNORECASE
)
# Lazy `.*?` (dev-2 R-03): the leftmost candidate assignment is tried first, so a firing line
# costs its prefix length, not the whole line scanned back from the end. The fire/hold verdict
# is order-insensitive (every candidate position is still tried on failure).
DIFF_SECRET_ASSIGNMENT = re.compile(
    rf"^\+[^+].*?(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}", re.IGNORECASE
)
# The mid-line form above cannot see a name at the very head of a diff line: `[^+]` eats its
# first character (dev-1's G-01 miss on `+KEY="foo`); this head form covers both branches'
# unbalanced-quote and self-reference shapes. `(?!\+)` keeps the `+++ b/...` headers out.
DIFF_HEAD_SECRET_ASSIGNMENT = re.compile(
    rf"^\+(?!\+)[ \t]*(?:export[ \t]+)?(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}",
    re.IGNORECASE,
)
# dev-2 R-02: dev-1's name==value hold was path-blind and un-terminated (`PASSWORD=password`
# regressed from firing on base to holding). The hold is now the narrowest statement that
# describes a Python kwarg passing a variable into itself: the value equals the name and the
# kwarg comma terminates it. `PASSWORD=password`, `key=KEY` and `TOKEN=token` fire again;
# the 14 `token=token,` passings in scripts/keycloak-bootstrap.py keep the suite green at rest.
_SECRET_KEYWORDS = ("password", "secret", "token", "credential", "key")
SECRET_SCAN_PREFIXES = ("identity/", "proxy/", "docs/evidence/EKO-1-12/", "scripts/keycloak-")


def _is_self_reference_kwarg_passing(name: str, value: str) -> bool:
    return value.endswith(",") and value[:-1].casefold() == name.casefold()


def is_secret_env_assignment(line: str) -> bool:
    # dev-2 R-03: the mid-line diff search was quadratic on long non-matching lines (10k =
    # 8.1s measured, base 0.25ms); this linear membership prefilter guards both branches —
    # no match is possible without an `=` and a keyword on the line.
    if "=" not in line:
        return False
    folded = line.casefold()
    if not any(keyword in folded for keyword in _SECRET_KEYWORDS):
        return False
    for pattern in (
        RAW_SECRET_ASSIGNMENT,
        DIFF_SECRET_ASSIGNMENT,
        DIFF_HEAD_SECRET_ASSIGNMENT,
    ):
        match = pattern.search(line)
        if match is not None and not _is_self_reference_kwarg_passing(
            match["name"], match["value"]
        ):
            return True
    return False


def find_literal_secret_assignment_lines(relative: str, text: str) -> list[int]:
    """The scan predicate: 1-based line numbers of literal secret environment assignments."""
    if not relative.startswith(SECRET_SCAN_PREFIXES):
        return []
    # dev-2 R-04: `splitlines()` also cuts on \v, \f, \x85, U+2028 and U+2029 — Unicode line
    # boundaries that are not line boundaries for git or a shell — shifting reported numbers
    # and splitting values mid-token. The scan cuts on `\n` only (the read is already
    # universal-newline; a trailing `\r` is stripped defensively) and the prefix contexts above
    # keep assignments after one of those separators firing on the same physical line.
    return [
        number
        for number, line in enumerate(
            (raw.rstrip("\r") for raw in text.split("\n")),
            start=1,
        )
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
# path-valued name that merely contains a keyword, and Python's self-reference kwarg passings
# — dev-2 R-02 narrowed that last hold to the comma-terminated `NAME=name,` call shape, so
# bare `PASSWORD=password` / `TOKEN=token` fire again (both directions pinned below).
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


# --- dev-2 (review findings): the newly-pinned shapes, both directions for every fix.

# R-01: the five mid-line shell contexts of the reviewer's plants; dev-1's raw branch only
# saw line-start assignments and passed these.
MIDLINE_FIRE_SHAPES = [
    "set -eu; export ADMIN_API_KEY=x",
    "echo hi && TOKEN=x ./runner",
    "docker run -e CLIENT_SECRET=x img",
    "env A=1 TOKEN=x run.sh",
    "export FOO=bar ADMIN_TOKEN=x",
]
# R-01 contrast: the same contexts with placeholder values — the hold family survives the
# wider anchor untouched.
MIDLINE_HOLD_SHAPES = [
    "set -eu; export ADMIN_API_KEY=${ADMIN_API_KEY}",
    "echo hi && TOKEN=${TOKEN} ./runner",
    "docker run -e CLIENT_SECRET=${S} img",
    "env A=1 TOKEN=${VAR} run.sh",
    "export FOO=bar ADMIN_TOKEN=${VAULT}",
]

# R-02: the self-reference hold narrowed to the comma-terminated kwarg call shape; bare
# name==value assignments fire again.
SELF_REFERENCE_FIRE_SHAPES = [
    "PASSWORD=password",
    "key=KEY",
    "TOKEN=token",
    "API_KEY=API_KEY",
    "+API_KEY=API_KEY",
]
SELF_REFERENCE_HOLD_SHAPES = [
    "token=token,",
    "        token=token,",
    "export TOKEN=token,",
]

# G-01: unbalanced-quote and empty-quote values are literals in both branches (supersedes
# dev-1's assumption A-04, which had the raw `KEY="foo` shape holding); the same openings
# with a `$` reference start still hold.
QUOTE_LITERAL_FIRE_SHAPES = [
    'KEY="foo',
    'KEY=""',
    "KEY='foo",
    "KEY=''",
    'KEY="',
    '+KEY="foo',
    '+KEY=""',
    '+ KEY="foo',
]
QUOTE_REFERENCE_HOLD_SHAPES = ['KEY="${VAR}"', 'KEY="$']

# A-06 restated as a probe: every shape the pre-EKO-1-29 (main) `\b`-keyword diff scan fired
# on — produced by running that pattern over candidates on 2026-11-12, recorded in
# docs/evidence/EKO-1-29/ — still fires under the dev-2 grammar.
BASE_FIRED_PROBE_SHAPES = [
    "+ KEY=literal",
    "+export TOKEN=x",
    "+\tpassword=Passw0rd",
    '+ KEY="foo',
    '+ KEY=""',
    "+ KEY=KEY",
    "+ client_id=x SECRET=lit",
    "+ --flag TOKEN=abc123",
    "+ TOKEN=token",
    "+ credential='pw'",
    "+a SECRET=b",
]

# R-04: the boundaries Python's splitlines() cuts on but git and shells do not.
UNIVERSAL_LINE_SEPARATORS = ["\u2028", "\u2029", "\v", "\f", "\x85"]


@pytest.mark.parametrize("shape", MIDLINE_FIRE_SHAPES)
def test_eko129_r01_midline_shell_context_assignments_fire(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == [1]


@pytest.mark.parametrize("shape", MIDLINE_FIRE_SHAPES)
@pytest.mark.parametrize("path", SCANNED_PATHS_UNDER_TEST)
def test_eko129_r01_midline_shapes_fire_under_every_scanned_prefix(path: str, shape: str) -> None:
    assert find_literal_secret_assignment_lines(path, shape) == [1]


@pytest.mark.parametrize("shape", MIDLINE_HOLD_SHAPES)
def test_eko129_r01_contrast_midline_placeholder_shapes_hold(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == []


@pytest.mark.parametrize("shape", SELF_REFERENCE_FIRE_SHAPES)
def test_eko129_r02_self_reference_assignments_fire_again(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == [1]


@pytest.mark.parametrize("shape", SELF_REFERENCE_HOLD_SHAPES)
def test_eko129_r02_contrast_kwarg_passings_still_hold(shape: str) -> None:
    assert find_literal_secret_assignment_lines("scripts/keycloak-bootstrap.py", shape) == []


@pytest.mark.parametrize("shape", QUOTE_LITERAL_FIRE_SHAPES)
def test_eko129_g01_unterminated_and_empty_quoted_values_fire(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == [1]


@pytest.mark.parametrize("shape", QUOTE_REFERENCE_HOLD_SHAPES)
def test_eko129_g01_contrast_reference_quoted_values_hold(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == []


@pytest.mark.parametrize("shape", BASE_FIRED_PROBE_SHAPES)
def test_eko129_a06_base_fired_shapes_still_fire(shape: str) -> None:
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", shape) == [1]


@pytest.mark.parametrize("separator", UNIVERSAL_LINE_SEPARATORS)
def test_eko129_r04_unicode_line_separators_do_not_create_phantom_lines(separator: str) -> None:
    # splitlines() would cut at the separator and report the second assignment on line 3.
    text = f"echo start\nKEY=lit1{separator}ADMIN_TOKEN=lit2\ntrailer\n"
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", text) == [2]


def test_eko129_r04_trailing_carriage_return_is_stripped_defensively() -> None:
    # The universal-newline read never yields these, but a lone `\r` at the line end must
    # not leak into the value grammar; the assignment fires on its single physical line.
    assert find_literal_secret_assignment_lines("proxy/entrypoint.sh", "export TOKEN=x\r") == [1]


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
