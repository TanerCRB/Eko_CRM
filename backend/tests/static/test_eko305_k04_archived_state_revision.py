"""EKO-3-05 K-04, static half (ADR-0002, ADR-0004 *Expand -> deploy -> contract* and the EKO-3-05
addendum draft, ADR-0002-C13, ADR-0005-C1; K-04 M-p5): revision 0008 only adds the nullable
`customer.archived_at` as an instant with its offset, on 0007; it sets no default the database
would evaluate, no NOT NULL, no timeout and writes no row, so an `INSERT` that names no such column
stores an active customer; and its docstring gives the column the ADR-0005 category PD-C4.

The runtime halves:
`tests/runtime/eko305/test_eko305_k04_archive_and_restore_change_only_the_state.py` (a row stored
without the column reads back active) and
`tests/runtime/test_eko305_k04_c37_previous_release_over_the_archived_state.py` (ADR-0004-C37).
"""

import ast
import re
from pathlib import Path

from tests.static.test_eko302_k06_expand_revision import (
    VERSIONS,
    added_columns,
    assigned,
    categories,
    upgrade,
)


def revision() -> Path:
    [found] = VERSIONS.glob("0008_*.py")
    return found


def violations(source: str) -> list[str]:
    body = ast.Module(body=[upgrade(ast.parse(source))], type_ignores=[])
    problems = []
    added = added_columns(source)
    if set(added) != {"archived_at"}:
        problems.append(f"columns added: {sorted(added)}")
    for name, column in added.items():
        keywords = {k.arg: k.value for k in column.keywords}
        nullable = keywords.get("nullable")
        if not (isinstance(nullable, ast.Constant) and nullable.value is True):
            problems.append(f"{name}: not nullable=True")
        for key in ("server_default", "default", "server_onupdate", "computed"):
            if key in keywords:
                problems.append(f"{name}: {key}")
        if "DateTime(timezone=True)" not in ast.unparse(column):
            problems.append(f"{name}: not an instant with its offset")
    used = {
        node.func.attr
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    }
    if used - {"add_column"}:
        problems.append(f"operations other than expand: {sorted(used)}")
    if re.search(r"timeout|now\(|SET |UPDATE |INSERT |DELETE ", ast.unparse(body), re.IGNORECASE):
        problems.append("a timeout, a clock or a row change in the revision")
    if categories(source).get("archived_at") != "PD-C4":
        problems.append("archived_at: not categorised PD-C4")
    return problems


def test_k04_revision_0008_adds_only_a_nullable_archived_instant_on_0007() -> None:
    source = revision().read_text(encoding="utf-8")
    assert violations(source) == []
    assert assigned(source, "revision") == ["0008"]
    assert assigned(source, "down_revision") == ["0007"]


def test_k04_contrast_a_planted_default_not_null_backfill_or_missing_category_is_found() -> None:
    source = revision().read_text(encoding="utf-8")
    assert "nullable=True" in source
    not_null = source.replace("nullable=True", "nullable=False", 1)
    assert any("not nullable" in p for p in violations(not_null))
    defaulted = source.replace("nullable=True", "nullable=True, server_default=sa.func.now()", 1)
    assert any("server_default" in p for p in violations(defaulted))
    backfill = source.replace(
        "def upgrade() -> None:\n",
        'def upgrade() -> None:\n    op.execute("UPDATE customer SET archived_at = now()")\n',
    )
    assert any("expand" in p or "row change" in p for p in violations(backfill))
    naive = source.replace("DateTime(timezone=True)", "DateTime()", 1)
    assert any("offset" in p for p in violations(naive))
    uncategorised = source.replace("PD-C4", "PD-C3")
    assert "archived_at: not categorised PD-C4" in violations(uncategorised)
