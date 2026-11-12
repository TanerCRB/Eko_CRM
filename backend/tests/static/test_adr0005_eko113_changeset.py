"""EKO-1-13 K-07 (b): what the change leaves as it was (DoD 13).

- Accepted ADR files change only by appended dated addenda.
- `create_app()`'s route table and its OpenAPI document equal the base branch's. Row 23's release
  comparator compares nothing until a second release exists, so the base branch is the reference
  here. No fixture path ships.
- `/api/health`'s body stays status-only.
- The EKO-1-11 refusal, EKO-1-14 backup and C28 test files are unchanged. The one exception is the
  statement-line parser of `test_adr0004_c15_backup_set_contents.py`, edited under the human's S-1
  decision on Issue #54; its diff is checked to be that parser and nothing else.

The route/OpenAPI and protected-test claims are about EKO-1-13's own change set and are judged on
PR #81's parents (EKO_1_13_BASE, EKO_1_13_HEAD), read through Git objects only (EKO-1-23, #110):
never `$CHANGESET_BASE`, `origin/main` or the working tree. What every branch must meet (health
body, no fixture route, a non-empty route read) is judged on the live head. The ADR addenda check
reads the live base, as `test_k07_changeset.py` does. The contrasts run on planted inputs.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.static.test_k07_changeset import adr_files_at_base, at_base, in_worktree
from tests.support import repo_checks as rc
from tests.support.fixed_pair import archive_into
from tests.support.repo import REPO_ROOT, git

# PR #81 (EKO-1-13): cc73e13's parents; its merge base is the first parent.
EKO_1_13_BASE = "1bfaa5aa57cb854739d230e24b42655d66d1270f"
EKO_1_13_HEAD = "947ff40efac06b13d6df48b6650024503f2e7308"

SURFACE = """
import json, os, sys
for name, value in (("APP_DB_PASSWORD", "synthetic-surface-only"), ("APP_DB_POOL_SIZE", "1"),
                    ("APP_DB_MAX_OVERFLOW", "0")):
    os.environ.setdefault(name, value)
from fastapi import routing
from app.main import create_app
from app.api.health import HealthStatus
app = create_app()
routes = sorted(f"{m} {c.path}" for c in routing.iter_route_contexts(app.routes)
                for m in sorted(getattr(c.route, "methods", None) or {"-"}))
sys.stdout.write(json.dumps({"routes": routes, "openapi": app.openapi(),
                             "health": sorted(HealthStatus.model_fields)}, sort_keys=True))
"""

Surface = dict[str, Any]

PROTECTED_TESTS = (
    "test_adr0004_c13_",
    "test_adr0006_c13_",
    "test_adr0004_c14_",
    "test_k04_c28_",
    "test_adr0005_backup_log_content.py",
    "test_adr0004_backup_failure_line.py",
)
# Human-decided edits of protected or EKO-1-14 tests (Issue #54): path -> the only lines that
# may change. S-1: the c15 statement-line parser; S-4: the c14 failure check by its cause.
ALLOWED_EDITS: dict[str, tuple[str, ...]] = {
    "backend/tests/runtime/test_adr0004_c15_backup_set_contents.py": (
        "LOGGED = re.compile(",
        "statement_logged_run(backup_lab)",
        "first_run = statement_logged_run(backup_lab)",
        "assert first_run, ",
    ),
    "backend/tests/runtime/test_adr0004_c14_failing_revision.py": (
        'assert "division by zero" in logs, logs[-2000:]',
        """assert '"cause":"psycopg.errors.DivisionByZero"' in logs, logs[-2000:]""",
    ),
}


def surface(backend_dir: Path) -> Surface:
    result = subprocess.run(
        [sys.executable, "-c", SURFACE],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    loaded: Surface = json.loads(result.stdout)
    return loaded


def surface_at(commit: str, target: Path) -> Surface:
    """The surface of `create_app()` as `commit` holds it; a missing commit raises."""
    archive_into(commit, target, "backend/app", "backend/migrations")
    return surface(target / "backend")


def pair_surfaces(
    root: Path, base: str = EKO_1_13_BASE, head: str = EKO_1_13_HEAD
) -> tuple[Surface, Surface]:
    return surface_at(base, root / "base"), surface_at(head, root / "head")


def surface_problems(base: Surface, head: Surface) -> list[str]:
    problems = []
    for key in ("routes", "openapi"):
        if base[key] != head[key]:
            problems.append(f"{key} differs from the base branch's")
    if head["health"] != ["status"]:
        problems.append(f"health body fields {head['health']}")
    if any("fixture" in route for route in head["routes"]):
        problems.append("a fixture route ships")
    return problems


@pytest.fixture(scope="module")
def surfaces(tmp_path_factory: pytest.TempPathFactory) -> tuple[Surface, Surface]:
    return pair_surfaces(tmp_path_factory.mktemp("pair"))


@pytest.fixture(scope="module")
def live_surface() -> Surface:
    return surface(REPO_ROOT / "backend")


def test_adr0005_eko113_changeset_route_table_openapi_and_health_body(
    surfaces: tuple[Surface, Surface], live_surface: Surface
) -> None:
    base, head = surfaces
    assert head["routes"], "no route read: the comparison would compare nothing"
    assert surface_problems(base, head) == []
    # The standing rules (ADR-0003-C23, ADR-0005: no fixture route ships) hold for the live head.
    assert live_surface["routes"], "no live route read: the live rules would check nothing"
    assert surface_problems(live_surface, live_surface) == []


def test_adr0005_eko113_changeset_adr_files_only_gain_addenda() -> None:
    """Live invariant: accepted ADR text changes only by appended dated addenda, on every branch."""
    problems = []
    for path in adr_files_at_base():
        base, head = at_base(path), in_worktree(path)
        if base is not None and head is not None:
            problems += [f"{path}: {p}" for p in rc.adr_append_only(base, head)]
    assert problems == []


def changed_lines(path: str, base: str, head: str) -> list[str]:
    diff = git("diff", "-U0", f"{base}^{{commit}}", f"{head}^{{commit}}", "--", path)
    return [
        line[1:].strip()
        for line in diff.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def protected_problems(changed: list[str], edits: dict[str, list[str]]) -> list[str]:
    """`edits`: path -> its changed lines, for the paths in ALLOWED_EDITS."""
    problems = [
        f"{path}: changed"
        for path in changed
        if path.rsplit("/", 1)[-1].startswith(PROTECTED_TESTS) and path not in ALLOWED_EDITS
    ]
    for path, lines in edits.items():
        allowed = ALLOWED_EDITS.get(path, ())
        problems += [
            f"{path}: {line!r} is outside the human-decided edit"
            for line in lines
            if line and not line.startswith(allowed) and not line.startswith("#")
        ]
    return problems


def eko_1_13_protected_problems(base: str = EKO_1_13_BASE, head: str = EKO_1_13_HEAD) -> list[str]:
    """`protected_problems` for what changed from `base` to `head`; a missing commit raises."""
    out = git(
        "diff", "--name-only", f"{base}^{{commit}}", f"{head}^{{commit}}", "--", "backend/tests"
    )
    edits = {path: changed_lines(path, base, head) for path in ALLOWED_EDITS}
    return protected_problems(out.split(), edits)


def test_adr0005_eko113_changeset_refusal_backup_and_c28_tests_unchanged() -> None:
    assert eko_1_13_protected_problems() == []


# Planted contrasts ---------------------------------------------------------------------------


def test_adr0005_eko113_changeset_contrast_planted_surface_changes_fail(
    surfaces: tuple[Surface, Surface],
) -> None:
    base, head = surfaces
    routes = [*head["routes"], "GET /api/fixture/boom"]
    assert surface_problems(base, {**head, "routes": routes}) != []
    assert surface_problems(base, {**head, "health": ["revision", "status"]}) != []
    assert surface_problems(base, {**head, "openapi": {"openapi": "3.1.0"}}) != []


def test_adr0005_eko113_changeset_contrast_planted_adr_edit_fails() -> None:
    path = adr_files_at_base()[0]
    base = at_base(path) or ""
    first = base.splitlines()[0]
    assert rc.adr_append_only(base, base.replace(first, first + " (edited)", 1)) != []


def test_adr0005_eko113_changeset_contrast_planted_test_edits_fail() -> None:
    changed = ["backend/tests/runtime/test_adr0004_backup_failure_line.py"]
    assert protected_problems(changed, {}) != []
    c14, c15 = sorted(ALLOWED_EDITS)
    assert protected_problems([c14], {c14: ["assert code == 0, logs"]}) != []
    assert protected_problems([c15], {c15: ["assert result.code == 1"]}) != []
    assert protected_problems([c14, c15], {c14: [], c15: []}) == []
