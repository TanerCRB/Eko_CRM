"""K-02 static half: backup receives the advisory-lock key as the YAML alias of compose.yaml's
`x-migration-advisory-lock`, and no file under backup/ holds the key (ADR-0004 addendum
2026-10-30, *One run*, step 1). The key is read from compose.yaml, never written here.
"""

from tests.static.conftest import COMPOSE
from tests.support import migration_checks as mc
from tests.support.source_checks import repository_sources

COMPOSE_TEXT = COMPOSE.read_text(encoding="utf-8")


def backup_files() -> dict[str, str]:
    return {path: text for path, text in repository_sources().items() if path.startswith("backup/")}


def test_k02_backup_takes_the_lock_key_by_reference() -> None:
    assert mc.backup_lock_reference_violations(COMPOSE_TEXT) == []
    assert mc.lock_reference_violations(COMPOSE_TEXT) == []


def test_k02_no_literal_of_the_key_under_backup() -> None:
    assert backup_files() != {}
    assert mc.files_holding(backup_files(), mc.lock_key(COMPOSE_TEXT)) == []


def backup_lock_line() -> tuple[list[str], int]:
    lines = COMPOSE_TEXT.splitlines()
    return lines, mc.environment_key_line(COMPOSE_TEXT, "backup", mc.LOCK_VARIABLE)


def test_k02_contrast_an_equal_literal_in_backups_environment_fails() -> None:
    lines, index = backup_lock_line()
    lines[index] = f'      {mc.LOCK_VARIABLE}: "{mc.lock_key(COMPOSE_TEXT)}"'
    planted = "\n".join(lines) + "\n"
    assert mc.backup_lock_reference_violations(planted) != []
    assert mc.lock_reference_violations(planted) != []


def test_k02_contrast_backup_without_the_key_fails() -> None:
    lines, index = backup_lock_line()
    del lines[index]
    assert mc.backup_lock_reference_violations("\n".join(lines) + "\n") != []


def test_k02_contrast_a_literal_under_backup_is_found() -> None:
    key = mc.lock_key(COMPOSE_TEXT)
    planted = {**backup_files(), "backup/eko-backup": f"KEY={key}\n"}
    assert mc.files_holding(planted, key) == ["backup/eko-backup"]
