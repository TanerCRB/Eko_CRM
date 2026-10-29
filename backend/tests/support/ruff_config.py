"""The ruff configuration that applies under backend/ (ADR-0001-C8, C11 as restated 2026-10-29)."""

import fnmatch
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from tests.support.layer_table import Row
from tests.support.repo import REPO_ROOT

CONFIG_NAMES = {"pyproject.toml", "ruff.toml", ".ruff.toml"}
ROOT_CONFIG = "backend/pyproject.toml"
EXTEND = "../../pyproject.toml"
# Every code that, listed in an ignore, switches S608 off.
S608_PREFIXES = {"ALL", "S", "S6", "S60", "S608"}


def is_config(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in CONFIG_NAMES


def tracked_configs(files: Mapping[str, str]) -> dict[str, str]:
    return {path: text for path, text in files.items() if is_config(path)}


def _parse(path: str, text: str, problems: list[str]) -> dict[str, Any] | None:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        problems.append(f"{path}: not valid TOML ({exc})")
        return None


def nested_paths(rows: list[Row]) -> dict[str, Row]:
    """`backend/app/<layer>/ruff.toml` for every backend layer row that forbids something."""
    found = {}
    for row in rows:
        match = re.fullmatch(r"backend/app/([a-z_]+)/\*\*", row.glob)
        if match and row.forbidden:
            found[f"backend/app/{match.group(1)}/ruff.toml"] = row
    return found


def _expected_bans(row: Row, rows: list[Row]) -> set[str]:
    prefixes = {r.name: r.prefixes for r in rows}
    return {prefix for layer in row.forbidden for prefix in prefixes.get(layer, ())}


def _nested_problems(path: str, config: dict[str, Any], row: Row, rows: list[Row]) -> list[str]:
    problems = []
    if config.get("extend") != EXTEND:
        problems.append(f"{path}: extend is {config.get('extend')!r}, not {EXTEND!r}")
    if set(config) - {"extend", "lint"}:
        problems.append(f"{path}: keys other than extend and banned-api: {sorted(set(config))}")
    lint = config.get("lint", {})
    tidy = lint.get("flake8-tidy-imports", {}) if isinstance(lint, dict) else {}
    if not isinstance(lint, dict) or set(lint) != {"flake8-tidy-imports"}:
        problems.append(f"{path}: lint holds more than flake8-tidy-imports.banned-api")
    if not isinstance(tidy, dict) or set(tidy) != {"banned-api"}:
        problems.append(f"{path}: flake8-tidy-imports holds more than banned-api")
        return problems
    banned = tidy["banned-api"]
    if not isinstance(banned, dict) or any(set(v) != {"msg"} for v in banned.values()):
        problems.append(f"{path}: banned-api entries must hold only msg")
        return problems
    expected = _expected_bans(row, rows)
    if set(banned) != expected:
        problems.append(
            f"{path}: bans {sorted(banned)}, the {row.name} row forbids {sorted(expected)}"
        )
    return problems


# R-03: keys that narrow what `ruff check .` lints, or switch the layer rules off for some files.
SCOPING_KEYS = {"exclude", "extend-exclude", "include", "extend-include", "force-exclude"}
LINT_SCOPING_KEYS = {"exclude", "extend-per-file-ignores"}
TID_PREFIXES = {"ALL", "TID", "TID2", "TID25", "TID251", "TID252"}


def _covers_tid(codes: object) -> bool:
    return isinstance(codes, list) and any(str(code) in TID_PREFIXES for code in codes)


def _root_scope_problems(path: str, ruff: Any) -> list[str]:
    if not isinstance(ruff, dict):
        return [f"{path}: [tool.ruff] is not a table"]
    raw_lint = ruff.get("lint")
    lint: dict[str, Any] = raw_lint if isinstance(raw_lint, dict) else {}
    problems = [f"{path}: [tool.ruff] sets {key}" for key in sorted(SCOPING_KEYS & set(ruff))]
    problems += [
        f"{path}: [tool.ruff.lint] sets {k}" for k in sorted(LINT_SCOPING_KEYS & set(lint))
    ]
    for table in (ruff, lint):
        for key in ("ignore", "extend-ignore"):
            if _covers_tid(table.get(key)):
                problems.append(f"{path}: {key} switches the layer rules (TID251, TID252) off")
        for glob, codes in (table.get("per-file-ignores") or {}).items():
            if not str(glob).startswith("tests/") and _covers_tid(codes):
                problems.append(f"{path}: per-file-ignores {glob!r} switches the layer rules off")
    return problems


@cache
def ruff_default_excludes() -> frozenset[str]:
    """The directory names ruff skips by default, as the installed ruff itself reports them."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--show-settings", "."],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
        check=True,
    )
    block = re.search(r"file_resolver\.exclude = \[(.*?)\]", result.stdout, re.DOTALL)
    if block is None:
        raise RuntimeError("ruff --show-settings no longer reports file_resolver.exclude")
    return frozenset(re.findall(r'"([^"]+)"', block.group(1)))


def default_excluded_sources(paths: list[str]) -> list[str]:
    """R-03: a tracked source below a directory ruff skips by default is never linted."""
    excludes = ruff_default_excludes()
    return [
        f"{path}: under {segment}/, which ruff does not lint by default"
        for path in paths
        if path.startswith("backend/") and path.endswith((".py", ".pyi"))
        for segment in path.split("/")[1:-1]
        if any(fnmatch.fnmatch(segment, pattern) for pattern in excludes)
    ]


def configuration_violations(files: Mapping[str, str], rows: list[Row]) -> list[str]:
    """The closed set (G-11 A): one `[tool.ruff]`, and six nested files holding only their bans."""
    problems: list[str] = []
    nested = nested_paths(rows)
    configs = tracked_configs(files)
    for path, text in sorted(configs.items()):
        config = _parse(path, text, problems)
        if config is None:
            continue
        name = path.rsplit("/", 1)[-1]
        if name == "pyproject.toml":
            has_ruff = "ruff" in config.get("tool", {})
            if path == ROOT_CONFIG and not has_ruff:
                problems.append(f"{path}: has no [tool.ruff]")
            elif path == ROOT_CONFIG:
                problems += _root_scope_problems(path, config["tool"]["ruff"])
            elif path != ROOT_CONFIG and has_ruff:
                problems.append(f"{path}: [tool.ruff] outside {ROOT_CONFIG}")
        elif path not in nested:
            problems.append(f"{path}: a ruff configuration outside the closed set")
        else:
            problems += _nested_problems(path, config, nested[path], rows)
    for path in sorted(set(nested) - set(configs)):
        problems.append(f"{path}: missing")
    if ROOT_CONFIG not in configs:
        problems.append(f"{ROOT_CONFIG}: missing")
    return problems


def _lint_tables(config: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """The tables a ruff configuration's lint options live in: top level and `lint`."""
    root = config.get("tool", {}).get("ruff", {}) if name == "pyproject.toml" else config
    if not isinstance(root, dict):
        return []
    tables = [root]
    if isinstance(root.get("lint"), dict):
        tables.append(root["lint"])
    return tables


def _covers_s608(codes: object) -> bool:
    return isinstance(codes, list) and any(str(code) in S608_PREFIXES for code in codes)


def s608_configuration_violations(files: Mapping[str, str]) -> list[str]:
    """Checklist rule 19: S608 stays selected and is ignored for no file under `backend/app/`."""
    problems: list[str] = []
    for path, text in sorted(tracked_configs(files).items()):
        config = _parse(path, text, problems)
        if config is None:
            continue
        tables = _lint_tables(config, path.rsplit("/", 1)[-1])
        selects = [t["select"] for t in tables if "select" in t]
        if path == ROOT_CONFIG and not selects:
            problems.append(f"{path}: no select, so S608 is not selected")
        for select in selects:
            if not _covers_s608(select):
                problems.append(f"{path}: select {select!r} does not include S608")
        for table in tables:
            for key in ("ignore", "extend-ignore"):
                if _covers_s608(table.get(key)):
                    problems.append(f"{path}: {key} switches S608 off")
            for key in ("per-file-ignores", "extend-per-file-ignores"):
                for glob, codes in (table.get(key) or {}).items():
                    if not str(glob).startswith("tests/") and _covers_s608(codes):
                        problems.append(f"{path}: {key} {glob!r} switches S608 off")
    return problems


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str


def lint_in_sandbox(
    sandbox: Path, configs: Mapping[str, str], fixtures: Mapping[str, str]
) -> list[Finding]:
    """Ruff run on fixture files placed beside copies of the tracked configurations.

    Paths are repository-relative; the sandbox holds nothing else, so nothing is ever tracked.
    """
    for relative, text in {**configs, **fixtures}.items():
        target = sandbox / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    command = [sys.executable, "-m", "ruff", "check", "--no-cache", "--exit-zero"]
    result = subprocess.run(
        [*command, "--output-format", "json", *fixtures],
        cwd=sandbox,
        capture_output=True,
        text=True,
        check=True,
    )
    root = sandbox.resolve()
    return [
        Finding(
            Path(item["filename"]).resolve().relative_to(root).as_posix(),
            item["location"]["row"],
            item["code"],
        )
        for item in json.loads(result.stdout)
    ]
