"""EKO-3-02 K-06, static half (ADR-0002, ADR-0004 *Expand → deploy → contract*, ADR-0005-C1):
revision 0005 only adds nullable columns to `customer` and one check constraint on the new `nip`
column; it sets no default, no NOT NULL, no timeout and writes no row; and its docstring gives
every column it adds an ADR-0005 category.

The runtime half (existing rows unchanged, the previous backend on the expanded schema, C26) is
`tests/runtime/test_eko302_k06_expand_on_customer.py`.
"""

import ast
import re
from pathlib import Path

from tests.support.repo import REPO_ROOT

VERSIONS = REPO_ROOT / "backend" / "migrations" / "versions"
CATEGORY = re.compile(r"`customer\.(?P<column>[a-z_]+)`")
CATEGORY_LINE = re.compile(r"^- (?P<columns>.+): (?P<category>PD-C[1-4])\b", re.MULTILINE)
EXPECTED = {
    "street",
    "postal_code",
    "town",
    "voivodeship",
    "county",
    "nip",
    "foreign_tax_id",
}


def revision() -> Path:
    [found] = VERSIONS.glob("0005_*.py")
    return found


def calls(tree: ast.Module, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == name
    ]


def upgrade(tree: ast.Module) -> ast.FunctionDef:
    [found] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"]
    return found


def added_columns(source: str) -> dict[str, ast.Call]:
    """Column name -> its `sa.Column(...)` call, for every `op.add_column` in `upgrade()`."""
    tree = ast.parse(source)
    body = ast.Module(body=[upgrade(tree)], type_ignores=[])
    added = {}
    for call in calls(body, "add_column"):
        table, column = call.args
        assert isinstance(table, ast.Constant) and table.value == "customer"
        assert isinstance(column, ast.Call)
        name = column.args[0]
        assert isinstance(name, ast.Constant) and isinstance(name.value, str)
        added[name.value] = column
    return added


def categories(source: str) -> dict[str, str]:
    # A list item may wrap onto indented continuation lines.
    docstring = (ast.get_docstring(ast.parse(source)) or "").replace("\n  ", " ")
    found: dict[str, str] = {}
    for line in CATEGORY_LINE.finditer(docstring):
        for column in CATEGORY.finditer(line.group("columns")):
            found[column.group("column")] = line.group("category")
    return found


def violations(source: str) -> list[str]:
    tree = ast.parse(source)
    body = ast.Module(body=[upgrade(tree)], type_ignores=[])
    problems = []
    added = added_columns(source)
    if set(added) != EXPECTED:
        problems.append(f"columns added: {sorted(added)}")
    for name, column in added.items():
        keywords = {k.arg: k.value for k in column.keywords}
        nullable = keywords.get("nullable")
        if not (isinstance(nullable, ast.Constant) and nullable.value is True):
            problems.append(f"{name}: not nullable=True")
        for key in ("server_default", "default", "server_onupdate", "computed"):
            if key in keywords:
                problems.append(f"{name}: {key}")
    used = {
        node.func.attr
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    }
    if used - {"add_column", "create_check_constraint", "f"}:
        problems.append(f"operations other than expand: {sorted(used)}")
    checks = calls(body, "create_check_constraint")
    if len(checks) != 1 or "nip" not in ast.unparse(checks[0]):
        problems.append("not exactly one check constraint, on nip")
    if re.search(r"timeout|SET |UPDATE |INSERT |DELETE ", ast.unparse(body), re.IGNORECASE):
        problems.append("a timeout or a row change in the revision")
    missing = EXPECTED - set(categories(source))
    if missing:
        problems.append(f"no ADR-0005 category: {sorted(missing)}")
    return problems


def test_k06_revision_0005_is_an_expand_step_with_every_column_categorised() -> None:
    source = revision().read_text(encoding="utf-8")
    assert violations(source) == []
    assert categories(source)["nip"] == "PD-C1"
    assert categories(source)["foreign_tax_id"] == "PD-C1"
    assert {categories(source)[c] for c in ("street", "postal_code", "town")} == {"PD-C2"}
    assert assigned(source, "down_revision") == ["0004"]


def assigned(source: str, name: str) -> list[object]:
    return [
        node.value.value
        for node in ast.parse(source).body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
        and isinstance(node.value, ast.Constant)
    ]


def test_k06_contrast_a_planted_not_null_default_or_missing_category_is_found() -> None:
    source = revision().read_text(encoding="utf-8")
    assert "nullable=True" in source
    not_null = source.replace("nullable=True", "nullable=False", 1)
    assert any("not nullable" in p for p in violations(not_null))
    defaulted = source.replace("nullable=True", "nullable=True, server_default='x'", 1)
    assert any("server_default" in p for p in violations(defaulted))
    backfill = source.replace(
        "def upgrade() -> None:\n",
        "def upgrade() -> None:\n    op.execute(\"UPDATE customer SET town = ''\")\n",
    )
    assert any("expand" in p or "row change" in p for p in violations(backfill))
    uncategorised = re.sub(r"`customer\.town`(, )?", "", source)
    assert "no ADR-0005 category: ['town']" in violations(uncategorised)
