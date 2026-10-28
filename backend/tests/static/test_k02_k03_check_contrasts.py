"""K-02 and K-03 contrasts: the database checks fail on single-change fixture values.

The same functions are applied to the running composition in tests/runtime/.
"""

import dataclasses
import shutil
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.support import db_checks as dc
from tests.support.repo import REPO_ROOT

GOOD_ROLES = {
    "eko_app": dc.Role("eko_app", False, False, False, 30),
    "eko_keycloak": dc.Role("eko_keycloak", False, False, False, 25),
    "eko_backup": dc.Role("eko_backup", False, False, False, 5),
}
GOOD_BUDGET = dc.Budget(
    app_limit=30,
    keycloak_limit=25,
    backup_limit=5,
    keycloak_pool_max=20,
    web_workers=2,
    web_pool_size=5,
    web_max_overflow=5,
    worker_pool_size=2,
    worker_max_overflow=0,
    max_connections=100,
    superuser_reserved=3,
)


def test_k02_c1_contrast_a_17x_server_fails() -> None:
    assert dc.c1_version(180006) == []
    assert dc.c1_version(170006) != []
    assert dc.c1_version(190000) != []


def test_k02_c2_contrast_a_second_head_fails(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    shutil.copytree(REPO_ROOT / "backend" / "migrations" / "versions", versions)
    (versions / "0002_second_root.py").write_text(
        'revision = "0002"\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n\n\n'
        "def upgrade() -> None:\n    pass\n\n\ndef downgrade() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "script.py.mako").write_text("", encoding="utf-8")
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    heads = ScriptDirectory.from_config(config).get_heads()
    output = "\n".join(f"{head} (head)" for head in heads)
    assert len(heads) == 2
    assert dc.c2_heads(output, ["0001"]) != []


def test_k02_c2_the_repository_has_one_head_and_the_check_reads_it() -> None:
    config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == ["0001"]
    assert dc.c2_heads("0001 (head)\n", ["0001"]) == []
    assert dc.c2_heads("0001 (head)\n", []) != []


@pytest.mark.parametrize(
    ("encoding", "provider", "locale"),
    [
        ("UTF8", "c", None),
        ("UTF8", "i", "pl_PL"),
        ("UTF8", "i", "pl-pl"),
        ("SQL_ASCII", "i", "pl-PL"),
    ],
)
def test_k02_c5_contrast_fails(encoding: str, provider: str, locale: str | None) -> None:
    assert dc.c5_database("UTF8", "i", "pl-PL") == []
    assert dc.c5_database(encoding, provider, locale) != []


def test_k02_c6_contrast_a_naive_timestamp_column_fails() -> None:
    assert dc.c6_naive_columns([]) == []
    assert dc.c6_naive_columns([("visit", "starts_at")]) != []


def test_k03_roles_pass_on_the_composition_values() -> None:
    assert dc.role_violations(GOOD_ROLES) == []


@pytest.mark.parametrize(
    ("role", "change"),
    [
        ("eko_backup", {"connection_limit": -1}),
        ("eko_app", {"connection_limit": 0}),
        ("eko_app", {"create_db": True}),
        ("eko_keycloak", {"create_role": True}),
        ("eko_keycloak", {"superuser": True}),
    ],
)
def test_k03_role_contrast_fails(role: str, change: dict[str, Any]) -> None:
    roles = dict(GOOD_ROLES)
    roles[role] = dataclasses.replace(roles[role], **change)
    assert dc.role_violations(roles) != []


def test_k03_public_connect_contrast_fails() -> None:
    assert dc.public_connect_violations({"eko": False, "keycloak": False}) == []
    assert dc.public_connect_violations({"eko": True, "keycloak": False}) != []
    assert dc.public_connect_violations({"eko": False}) != []


def test_k03_c19_budget_passes_on_the_composition_values() -> None:
    assert dc.c19_violations(GOOD_BUDGET) == []


@pytest.mark.parametrize(
    "change",
    [
        # Three limits summing to exactly max_connections - superuser_reserved: the bound is strict.
        {"app_limit": 30, "keycloak_limit": 25, "backup_limit": 42},
        {"backup_limit": -1},
        {"backup_limit": 0},
        {"keycloak_pool_max": 26},
        {"web_workers": 3},
    ],
)
def test_k03_c19_contrast_fails(change: dict[str, int]) -> None:
    assert dc.c19_violations(dataclasses.replace(GOOD_BUDGET, **change)) != []
