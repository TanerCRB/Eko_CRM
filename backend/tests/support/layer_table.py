"""docs/architecture/layer-dependencies.md as data, read by the rules layer-check.sh uses."""

import ast
import re
from dataclasses import dataclass

from tests.support.repo import REPO_ROOT

TABLE_PATH = REPO_ROOT / "docs" / "architecture" / "layer-dependencies.md"
NONE_CELL = {"", "—", "-"}


@dataclass(frozen=True)
class Row:
    name: str
    glob: str
    prefixes: tuple[str, ...]
    forbidden: tuple[str, ...]

    def matches(self, path: str) -> bool:
        return glob_regex(self.glob).fullmatch(path) is not None


def glob_regex(glob: str) -> re.Pattern[str]:
    # As in layer-check.sh: `*` and `**` both match across directories.
    return re.compile(".*".join(re.escape(part) for part in re.split(r"\*+", glob)))


def _unquote(cell: str) -> str:
    cell = cell.strip()
    return cell[1:-1] if len(cell) >= 2 and cell[0] == cell[-1] == "`" else cell


def _list(cell: str) -> tuple[str, ...]:
    values = (_unquote(v) for v in cell.split(","))
    return tuple(v for v in values if v not in NONE_CELL)


def read_rows(text: str) -> list[Row]:
    rows = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.startswith("|") or "<" in line:
            continue
        cells = line.split("|")[1:-1]
        if len(cells) < 4:
            continue
        name, glob = cells[0].strip(), cells[1].strip()
        if not (re.fullmatch(r"`[^`]+`", name) and re.fullmatch(r"`[^`]+`", glob)):
            continue
        rows.append(Row(_unquote(name), _unquote(glob), _list(cells[2]), _list(cells[3])))
    return rows


def table_rows() -> list[Row]:
    return read_rows(TABLE_PATH.read_text(encoding="utf-8"))


def row_for(path: str, rows: list[Row]) -> Row | None:
    found = [row for row in rows if row.matches(path)]
    return found[0] if len(found) == 1 else None


def layer_of_module(module: str, rows: list[Row]) -> str | None:
    """The longest "Referenced as" prefix matching on a `.` boundary, as layer-check.sh reads it."""
    best, length = None, 0
    for row in rows:
        for prefix in row.prefixes:
            if len(prefix) > length and (module == prefix or module.startswith(prefix + ".")):
                best, length = row.name, len(prefix)
    return best


def _package(path: str) -> list[str]:
    """`backend/app/worker.py` is the module `app.worker`, in the package `app`."""
    parts = path.split("/")
    if parts[0] == "backend":
        parts = parts[1:]
    return parts[:-1]


def imported_modules(source: str, path: str) -> list[tuple[int, str]]:
    """Every module an import statement anywhere in the file names, with its line.

    `from app import api` names both `app` and `app.api`: the name imported may be a module.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source.replace("\r\n", "\n"))):
        if isinstance(node, ast.Import):
            found += [(alias.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package = _package(path)
                anchor = package[: len(package) - node.level + 1]
                base = ".".join([*anchor, *([base] if base else [])])
            if base:
                found.append((node.lineno, base))
            found += [
                (alias.lineno, f"{base}.{alias.name}" if base else alias.name)
                for alias in node.names
                if alias.name != "*"
            ]
    return sorted(found)


def whole_file_findings(path: str, source: str, rows: list[Row]) -> list[str]:
    """Every import of the file, judged against the row the file falls under (G-8 A)."""
    row = row_for(path, rows)
    if row is None:
        return []
    findings = []
    seen = set()
    for line, module in imported_modules(source, path):
        target = layer_of_module(module, rows)
        if target in row.forbidden and (line, target) not in seen:
            seen.add((line, target))
            findings.append(f"{path}:{line}: {row.name} must not depend on {target}: {module}")
    return findings
