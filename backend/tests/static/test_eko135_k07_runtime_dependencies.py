"""EKO-1-35 K-07: nothing the task adds runs in the browser or the backend at runtime: the runtime
`dependencies` of `frontend/package.json` and `[project].dependencies` of `backend/pyproject.toml`
are the base's. Under G-1 A (comparison) no manifest changes, so this holds trivially here.

Judged against the change set's base (`test_k07_changeset`); once the checker is in the base, a
later change set is not this one. The contrasts never read the base.
"""

import json
import tomllib

from tests.static.test_k07_changeset import at_base, in_worktree

CHECKER = "backend/tests/support/frontend_contract.py"
PACKAGE = "frontend/package.json"
PYPROJECT = "backend/pyproject.toml"


def is_eko135_change_set() -> bool:
    return at_base(CHECKER) is None


def runtime_dependency_changes(
    package: tuple[str | None, str | None], pyproject: tuple[str | None, str | None]
) -> list[str]:
    """Each manifest whose runtime dependencies differ from the base's, or that is missing."""
    problems = []
    if None in package:
        problems.append(f"{PACKAGE}: missing")
    elif json.loads(str(package[0])).get("dependencies") != json.loads(str(package[1])).get(
        "dependencies"
    ):
        problems.append(f"{PACKAGE}: dependencies differ from the base")
    if None in pyproject:
        problems.append(f"{PYPROJECT}: missing")
    elif tomllib.loads(str(pyproject[0]))["project"].get("dependencies") != tomllib.loads(
        str(pyproject[1])
    )["project"].get("dependencies"):
        problems.append(f"{PYPROJECT}: [project].dependencies differ from the base")
    return problems


def test_eko135_k07_runtime_dependencies_equal_the_base() -> None:
    if not is_eko135_change_set():
        return
    package = (at_base(PACKAGE), in_worktree(PACKAGE))
    pyproject = (at_base(PYPROJECT), in_worktree(PYPROJECT))
    assert runtime_dependency_changes(package, pyproject) == []


PACKAGE_TEXT = json.dumps(
    {"dependencies": {"react": "19.0.0"}, "devDependencies": {"vitest": "3.0.0"}}, indent=2
)
PYPROJECT_TEXT = (
    '[project]\nname = "x"\ndependencies = ["fastapi>=0.1"]\n\n'
    '[dependency-groups]\ndev = ["pytest>=8"]\n'
)


def _package(section: str, name: str) -> str:
    loaded = json.loads(PACKAGE_TEXT)
    loaded[section][name] = "1.0.0"
    return json.dumps(loaded, indent=2)


def test_eko135_k07_a_dev_dependency_passes() -> None:
    same = (PYPROJECT_TEXT, PYPROJECT_TEXT)
    assert (
        runtime_dependency_changes((PACKAGE_TEXT, _package("devDependencies", "zod")), same) == []
    )
    dev = PYPROJECT_TEXT.replace('dev = ["pytest>=8"]', 'dev = ["pytest>=8", "tree-sitter>=0.1"]')
    assert runtime_dependency_changes((PACKAGE_TEXT, PACKAGE_TEXT), (PYPROJECT_TEXT, dev)) == []


def test_eko135_k07_a_runtime_dependency_fails() -> None:
    same_pyproject = (PYPROJECT_TEXT, PYPROJECT_TEXT)
    frontend = (PACKAGE_TEXT, _package("dependencies", "zod"))
    assert runtime_dependency_changes(frontend, same_pyproject) != []
    runtime = PYPROJECT_TEXT.replace('["fastapi>=0.1"]', '["fastapi>=0.1", "jsonschema>=4"]')
    backend = (PYPROJECT_TEXT, runtime)
    assert runtime_dependency_changes((PACKAGE_TEXT, PACKAGE_TEXT), backend) != []


def test_eko135_k07_a_missing_manifest_fails() -> None:
    same_pyproject = (PYPROJECT_TEXT, PYPROJECT_TEXT)
    assert runtime_dependency_changes((PACKAGE_TEXT, None), same_pyproject) != []
