"""The backend's ruff configuration: no security rule switched off for production code."""

import tomllib

from tests.support.repo import REPO_ROOT


def ruff_lint() -> dict[str, object]:
    pyproject = tomllib.loads((REPO_ROOT / "backend" / "pyproject.toml").read_text("utf-8"))
    lint: dict[str, object] = pyproject["tool"]["ruff"]["lint"]
    return lint


def test_no_security_rule_is_ignored_project_wide() -> None:
    ignored = ruff_lint().get("ignore", [])
    assert isinstance(ignored, list)
    assert [rule for rule in ignored if str(rule).startswith("S")] == []


def test_production_code_ignores_only_the_documented_bind_rule() -> None:
    per_file = ruff_lint().get("per-file-ignores", {})
    assert isinstance(per_file, dict)
    production = {glob: rules for glob, rules in per_file.items() if not glob.startswith("tests/")}
    assert production == {"app/serve.py": ["S104"]}
