"""K-07 static half: the real tree is exactly {0001, 0002, 0003}; nothing adds a revision location,
so the test-only revisions under backend/tests/ are reachable only through a variant image."""

from typing import Any

import pytest

from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

ALEMBIC_INI = (REPO_ROOT / "backend" / "alembic.ini").read_text(encoding="utf-8")
VERSIONS = REPO_ROOT / "backend" / "migrations" / "versions"
TEST_REVISIONS = REPO_ROOT / "backend" / "tests" / "runtime" / "revisions"


def real_tree_files() -> list[str]:
    return sorted(p.name for p in VERSIONS.iterdir() if p.is_file() and p.suffix == ".py")


def test_adr0002_c2_real_tree_holds_exactly_the_three_revision_files() -> None:
    files = real_tree_files()
    assert len(files) == 3
    assert files[0].startswith("0001_")
    assert files[1].startswith("0002_")
    assert files[2].startswith("0003_")
    assert not set(files) & {p.name for p in TEST_REVISIONS.glob("*.py")}


def test_adr0002_c2_backend_build_context_excludes_the_test_revisions() -> None:
    ignored = (REPO_ROOT / "backend" / ".dockerignore").read_text(encoding="utf-8").split()
    assert "tests" in ignored


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_adr0002_c2_no_revision_location_is_added(
    profile: str, rendered_dev: dict[str, Any], rendered_shared: dict[str, Any]
) -> None:
    rendered = rendered_dev if profile == "dev" else rendered_shared
    assert mc.version_location_violations(ALEMBIC_INI, rendered) == []


def test_adr0002_c2_revision_location_check_fails_on_version_locations_in_alembic_ini(
    rendered_shared: dict[str, Any],
) -> None:
    planted = ALEMBIC_INI.replace(
        "prepend_sys_path = .\n", "prepend_sys_path = .\nversion_locations = tests/runtime\n"
    )
    assert planted != ALEMBIC_INI
    assert mc.version_location_violations(planted, rendered_shared) != []


def test_adr0002_c2_revision_location_check_fails_on_a_moved_script_location(
    rendered_shared: dict[str, Any],
) -> None:
    planted = ALEMBIC_INI.replace("%(here)s/migrations", "%(here)s/tests/runtime")
    assert mc.version_location_violations(planted, rendered_shared) != []


def test_adr0002_c2_revision_location_check_fails_on_a_service_setting_it(
    rendered_shared: dict[str, Any],
) -> None:
    services = dict(rendered_shared["services"])
    services["migrate"] = {
        **services["migrate"],
        "command": ["alembic", "-x", "version_locations=tests/runtime", "upgrade", "head"],
    }
    assert mc.version_location_violations(ALEMBIC_INI, {"services": services}) != []
