"""EKO-3-06, gate 1 A-2 A (ADR-0005-C1, ADR-0004 *Expand -> deploy -> contract*, the draft's
section 3): the dataset key of a seeded record is one nullable column on `customer`, added by one
expand revision on the head of `main` with a unique index and nothing else: no default, no NOT
NULL, no backfill, no timeout, and an ADR-0005 category ("not personal data") in its docstring.

The model matches it (`alembic check` is the runtime half, ADR-0002-C3).
"""

import ast
import re
from pathlib import Path

from app.data.models import DATASET_KEY_UNIQUE, CustomerRow
from tests.static.test_eko302_k06_expand_revision import assigned, calls, upgrade
from tests.support.repo import REPO_ROOT

VERSIONS = REPO_ROOT / "backend" / "migrations" / "versions"
COLUMN = "dataset_key"
CATEGORY = re.compile(r"^- `customer\.dataset_key`: not personal data\b", re.MULTILINE)


def revision() -> Path:
    [found] = VERSIONS.glob("0008_*.py")
    return found


def violations(source: str) -> list[str]:
    tree = ast.parse(source)
    body = ast.Module(body=[upgrade(tree)], type_ignores=[])
    problems = []
    added = calls(body, "add_column")
    names = [
        ast.unparse(call.args[1].args[0]) for call in added if isinstance(call.args[1], ast.Call)
    ]
    if names != [repr(COLUMN)]:
        problems.append(f"columns added: {names}")
    for call in added:
        column = call.args[1]
        assert isinstance(column, ast.Call)
        keywords = {k.arg: k.value for k in column.keywords}
        nullable = keywords.get("nullable")
        if not (isinstance(nullable, ast.Constant) and nullable.value is True):
            problems.append("not nullable=True")
        for key in ("server_default", "default", "server_onupdate", "computed"):
            if key in keywords:
                problems.append(key)
    used = {
        node.func.attr
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    }
    if used - {"add_column", "create_index", "f"}:
        problems.append(f"operations other than expand: {sorted(used)}")
    indexes = calls(body, "create_index")
    if len(indexes) != 1 or not any(
        k.arg == "unique" and isinstance(k.value, ast.Constant) and k.value.value is True
        for k in indexes[0].keywords
    ):
        problems.append("not exactly one unique index")
    if re.search(r"timeout|SET |UPDATE |INSERT |DELETE ", ast.unparse(body), re.IGNORECASE):
        problems.append("a timeout or a row change in the revision")
    if not CATEGORY.search(ast.get_docstring(tree) or ""):
        problems.append("no ADR-0005 category for customer.dataset_key")
    return problems


def test_eko306_a2_revision_0008_adds_only_the_nullable_unique_dataset_key() -> None:
    source = revision().read_text(encoding="utf-8")
    assert violations(source) == []
    assert assigned(source, "revision") == ["0008"]
    assert assigned(source, "down_revision") == ["0007"]
    assert DATASET_KEY_UNIQUE in source


def test_eko306_a2_the_model_declares_the_column_nullable_with_its_unique_index() -> None:
    table = CustomerRow.metadata.tables["customer"]
    column = table.c[COLUMN]
    assert column.nullable is True
    assert column.server_default is None and column.default is None
    [index] = [i for i in table.indexes if i.name == DATASET_KEY_UNIQUE]
    assert index.unique is True
    assert [c.name for c in index.columns] == [COLUMN]


def test_eko306_a2_contrast_a_planted_not_null_backfill_or_missing_category_is_found() -> None:
    source = revision().read_text(encoding="utf-8")
    assert "nullable=True" in source
    assert "not nullable=True" in violations(source.replace("nullable=True", "nullable=False", 1))
    defaulted = source.replace("nullable=True", "nullable=True, server_default='x'", 1)
    assert "server_default" in violations(defaulted)
    backfill = source.replace(
        "def upgrade() -> None:\n",
        "def upgrade() -> None:\n    op.execute(\"UPDATE customer SET dataset_key = 'k'\")\n",
    )
    assert any("expand" in p or "row change" in p for p in violations(backfill))
    assert "not exactly one unique index" in violations(
        source.replace("unique=True", "unique=False")
    )
    uncategorised = source.replace("not personal data", "unclassified")
    assert "no ADR-0005 category for customer.dataset_key" in violations(uncategorised)
