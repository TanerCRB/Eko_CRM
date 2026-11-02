"""EKO-1-13 K-07 (b): what the change leaves as it was (DoD 13).

- Accepted ADR files change only by appended dated addenda.
- `create_app()`'s route table and its OpenAPI document equal the base branch's. Row 23's release
  comparator compares nothing until a second release exists, so the base branch is the reference
  here. No fixture path ships.
- `/api/health`'s body stays status-only.
- The EKO-1-11 refusal, EKO-1-14 backup and C28 test files are unchanged. The one exception is the
  statement-line parser of `test_adr0004_c15_backup_set_contents.py`, edited under the human's S-1
  decision on Issue #54; its diff is checked to be that parser and nothing else.

Base: $CHANGESET_BASE, else origin/main (as `test_k07_changeset.py`). Once merged, base and head
are equal and every comparison holds trivially. The contrasts therefore run on planted inputs,
never on the live base.
"""

import json
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from tests.static.test_k07_changeset import adr_files_at_base, at_base, in_worktree, merge_base
from tests.support import repo_checks as rc
from tests.support.repo import REPO_ROOT, git

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


def base_backend(target: Path) -> Path:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", merge_base(), "backend/app", "backend/migrations"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        tar.extractall(target, filter="data")
    return target / "backend"


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
def surfaces(tmp_path_factory: pytest.TempPathFactory) -> tuple[Surface, ...]:
    base = surface(base_backend(tmp_path_factory.mktemp("base")))
    return base, surface(REPO_ROOT / "backend")


def test_adr0005_eko113_changeset_route_table_openapi_and_health_body(
    surfaces: tuple[Surface, Surface],
) -> None:
    base, head = surfaces
    assert head["routes"], "no route read: the comparison would compare nothing"
    assert surface_problems(base, head) == []


def test_adr0005_eko113_changeset_adr_files_only_gain_addenda() -> None:
    problems = []
    for path in adr_files_at_base():
        base, head = at_base(path), in_worktree(path)
        if base is not None and head is not None:
            problems += [f"{path}: {p}" for p in rc.adr_append_only(base, head)]
    assert problems == []


def changed_lines(path: str) -> list[str]:
    diff = git("diff", "-U0", merge_base(), "--", path)
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


def test_adr0005_eko113_changeset_refusal_backup_and_c28_tests_unchanged() -> None:
    out = git("diff", "--name-only", merge_base(), "--", "backend/tests")
    edits = {path: changed_lines(path) for path in ALLOWED_EDITS}
    assert protected_problems(out.split(), edits) == []


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
