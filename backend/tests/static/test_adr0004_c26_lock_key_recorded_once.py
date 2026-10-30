"""K-01 static half: the advisory-lock key is written once, as the top-level field
`x-migration-advisory-lock` of compose.yaml, and migrate's MIGRATION_ADVISORY_LOCK_KEY is that field
(ADR-0004 addendum 2026-10-29, *The advisory lock's identity*). The key is read from the file,
never written in a test.
"""

from tests.static.conftest import COMPOSE
from tests.support import migration_checks as mc
from tests.support.source_checks import repository_sources

COMPOSE_TEXT = COMPOSE.read_text(encoding="utf-8")


def test_adr0004_c26_lock_key_recorded_once() -> None:
    key = mc.lock_key(COMPOSE_TEXT)
    assert key != 0
    assert -(2**63) <= key < 2**63
    assert mc.files_holding(repository_sources(), key) == ["compose.yaml"]
    assert mc.lock_reference_violations(COMPOSE_TEXT) == []


def test_adr0004_c26_lock_key_recorded_once_fails_on_a_second_literal() -> None:
    key = mc.lock_key(COMPOSE_TEXT)
    files = {**repository_sources(), "backend/app/core/lock.py": f"MIGRATION_LOCK = {key}\n"}
    assert mc.files_holding(files, key) == ["backend/app/core/lock.py", "compose.yaml"]


def test_adr0004_c26_lock_key_recorded_once_ignores_tests_and_longer_numbers() -> None:
    key = mc.lock_key(COMPOSE_TEXT)
    files = {
        "compose.yaml": COMPOSE_TEXT,
        "backend/tests/x.py": f"K = {key}\n",
        "docs/x.md": f"{key}1 and 1{key}\n",
    }
    assert mc.files_holding(files, key) == ["compose.yaml"]


def test_adr0004_c26_lock_key_recorded_once_fails_when_migrate_repeats_the_value() -> None:
    key = mc.lock_key(COMPOSE_TEXT)
    lines = [
        line
        for line in COMPOSE_TEXT.splitlines()
        if line.strip().startswith(mc.LOCK_VARIABLE + ":")
    ]
    assert len(lines) == 1
    planted = COMPOSE_TEXT.replace(lines[0], f'      {mc.LOCK_VARIABLE}: "{key}"')
    assert mc.lock_reference_violations(planted) != []


def test_adr0004_c26_lock_key_recorded_once_fails_without_the_field() -> None:
    planted = COMPOSE_TEXT.replace(mc.LOCK_FIELD, "x-other-field")
    assert mc.lock_reference_violations(planted) != []
