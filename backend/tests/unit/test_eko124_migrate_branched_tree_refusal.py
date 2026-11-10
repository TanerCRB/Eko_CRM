"""EKO-1-24: a branched revision tree refuses naming every head, before any connection.

K-02 (the real env.py, run through Alembic's command API, refuses a two-head tree with no engine
created and before migrate's own settings are read), K-03 (an unresolvable identifier still reads
exactly "migrate refused: unknown destination revision" and a plain non-head identifier keeps its
line) and K-01's edge (a) (a three-head tree names all three). The refusal itself, applies-nothing
and the leak check are proven on the runtime surface
(`tests/runtime/test_eko124_migrate_branched_tree_refusal.py`).

The fixture aligns both tree views env.py's refusal consults — Alembic's script resolution (the
Config's `version_locations`) and the code-side read (`schema_revision.VERSIONS_DIR`) — to one and
the same temporary tree, the K-02 fixture condition: a fixture that branched only one view would
pass or fail depending on the fix mechanism. `script_location` stays the repository's real
`backend/migrations`, so the env.py that runs is the shipped file itself.
"""

import shutil
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config

from app.data import schema_revision
from tests.support.repo import REPO_ROOT
from tests.unit.conftest import SYNTHETIC_PASSWORD, closed_local_port

MIGRATIONS = REPO_ROOT / "backend" / "migrations"
SHIPPED_VERSIONS = MIGRATIONS / "versions"
FIXTURE_REVISIONS = REPO_ROOT / "backend" / "tests" / "runtime" / "revisions"
MIGRATE_ONLY = (
    "MIGRATION_ADVISORY_LOCK_KEY",
    "MIGRATION_LOCK_TIMEOUT_SECONDS",
    "MIGRATION_STATEMENT_TIMEOUT_SECONDS",
)


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    for name, value in {
        "APP_DB_HOST": "127.0.0.1",
        "APP_DB_PORT": str(closed_local_port()),
        "APP_DB_POOL_SIZE": "1",
        "APP_DB_MAX_OVERFLOW": "0",
        "APP_DB_CONNECT_TIMEOUT_SECONDS": "1",
        "MIGRATION_ADVISORY_LOCK_KEY": "424242",
        "MIGRATION_LOCK_TIMEOUT_SECONDS": "5",
        "MIGRATION_STATEMENT_TIMEOUT_SECONDS": "30",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("APP_DB_PASSWORD", SYNTHETIC_PASSWORD)
    created: list[str] = []
    real = sqlalchemy.create_engine

    def recording(*args: Any, **kwargs: Any) -> Any:
        created.append("engine")
        return real(*args, **kwargs)

    # env.py is executed afresh by Alembic and imports create_engine from sqlalchemy each time.
    monkeypatch.setattr(sqlalchemy, "create_engine", recording)
    return created


@pytest.fixture
def engines_without_migrate_settings(
    engines: list[str], monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    for name in MIGRATE_ONLY:
        monkeypatch.delenv(name, raising=False)
    return engines


def temp_tree(monkeypatch: pytest.MonkeyPatch, root: Path, *added: str) -> Path:
    """The shipped revisions plus `added`, as the one tree both views see."""
    versions = root / "versions"
    versions.mkdir()
    for path in sorted(SHIPPED_VERSIONS.glob("*.py")):
        shutil.copyfile(path, versions / path.name)
    for name in added:
        shutil.copyfile(FIXTURE_REVISIONS / name, versions / name)
    monkeypatch.setattr(schema_revision, "VERSIONS_DIR", versions)
    return versions


def alembic_config(versions: Path | None = None) -> Config:
    # No file name, so env.py does not reconfigure logging inside the test process.
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("path_separator", "os")
    if versions is not None:
        config.set_main_option("version_locations", str(versions))
    return config


def test_eko124_k02_branched_tree_refuses_naming_the_heads_before_any_engine(
    engines: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    versions = temp_tree(monkeypatch, tmp_path, "t_sibling_a.py", "t_sibling_b.py")
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(versions), "head")
    message = str(stopped.value.code)
    assert message.startswith("migrate refused:")
    assert "t_sibling_a" in message, message
    assert "t_sibling_b" in message, message
    assert engines == []


def test_eko124_k02_contrast_one_head_tree_reaches_the_database(
    engines: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    versions = temp_tree(monkeypatch, tmp_path, "t_sibling_a.py")
    with pytest.raises(sqlalchemy.exc.OperationalError):
        command.upgrade(alembic_config(versions), "head")
    assert engines == ["engine"]


def test_eko124_k02_edge_refusal_precedes_migrate_own_settings(
    engines_without_migrate_settings: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    versions = temp_tree(monkeypatch, tmp_path, "t_sibling_a.py", "t_sibling_b.py")
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(versions), "head")
    message = str(stopped.value.code)
    assert message.startswith("migrate refused:")
    assert "t_sibling_a" in message, message
    assert "t_sibling_b" in message, message
    assert "configuration error" not in message, message
    assert engines_without_migrate_settings == []


def test_eko124_k01_edge_three_head_tree_names_every_head(
    engines: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    versions = temp_tree(monkeypatch, tmp_path, "t_sibling_a.py", "t_sibling_b.py", "t_next.py")
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(versions), "head")
    message = str(stopped.value.code)
    assert message.startswith("migrate refused:")
    for head in ("t_sibling_a", "t_sibling_b", "t_next"):
        assert head in message, message
    assert engines == []


def test_eko124_k03_unresolvable_identifier_keeps_its_exact_line(engines: list[str]) -> None:
    # The shipped one-head tree: no version_locations, no patched code-side read.
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(), "zzz@head")
    # Whole-string equality: no head identifier, no raw Alembic text, no wrapped error line.
    assert str(stopped.value.code) == "migrate refused: unknown destination revision"
    assert engines == []


def test_eko124_k03_contrast_branched_tree_flips_to_the_heads_line(
    engines: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    versions = temp_tree(monkeypatch, tmp_path, "t_sibling_a.py", "t_sibling_b.py")
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(versions), "head")
    message = str(stopped.value.code)
    assert message.startswith("migrate refused:")
    assert "t_sibling_a" in message, message
    assert "t_sibling_b" in message, message
    assert message != "migrate refused: unknown destination revision"
    assert engines == []


def test_eko124_k03_edge_plain_unknown_identifier_keeps_the_head_line(engines: list[str]) -> None:
    # Alembic resolves a plain unknown identifier to itself; only the head check refuses it.
    with pytest.raises(SystemExit) as stopped:
        command.upgrade(alembic_config(), "zzz")
    message = str(stopped.value.code)
    assert message == "migrate refused: it upgrades only to the code's head (0002)"
    assert engines == []
