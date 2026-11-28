"""EKO-4-01, revision 0010 (ADR-0004 *Expand -> deploy -> contract*; ADR-0005-C1; ADR-0006 *Visit
identifiers are never reused*; ADR-0002-C13; the accepted addendum, sections 4 and 6; K-01 (d) and
K-05): the revision only creates the visit table, on 0009. `id` is a UUID with no sequence,
identity or default the database evaluates, so only the application issues identifiers;
`customer_id` is NOT NULL with a foreign key to the customer and no cascading action; the two
instants carry their offset; no column holds a state and none has a database default; it sets no
timeout and writes no row; and its docstring gives every column its ADR-0005 category.

The runtime halves: `tests/runtime/test_eko401_k01_visit_identifiers_after_a_restore.py` (no
identifier issued again after a restore) and the schema test of
`tests/runtime/eko401/test_eko401_k05_state_derived_from_the_clock.py` (no state column).
"""

import ast
import re
from pathlib import Path

from tests.static.test_eko302_k06_expand_revision import VERSIONS, assigned, calls, upgrade

COLUMNS = {
    "id": "not personal data",
    "customer_id": "PD-C4",
    "owner_subject": "PD-C4",
    "starts_at": "PD-C4",
    "ends_at": "PD-C4",
    "own_address": "PD-C2",
}
NULLABLE = {"own_address"}
INSTANTS = {"starts_at", "ends_at"}
CATEGORY_LINE = re.compile(
    r"^- (?P<columns>.+): (?P<category>PD-C[1-4]|not personal data)\b", re.MULTILINE
)
VISIT_COLUMN = re.compile(r"`visit\.(?P<column>[a-z_]+)`")
# A value the database would issue: a sequence, an identity or a generated UUID.
ISSUED = re.compile(r"Identity|Sequence|autoincrement|gen_random_uuid|uuid", re.IGNORECASE)
DEFAULTS = ("server_default", "default", "server_onupdate", "onupdate", "computed", "identity")


def revision() -> Path:
    [found] = VERSIONS.glob("0010_*.py")
    return found


def categories(source: str) -> dict[str, str]:
    docstring = (ast.get_docstring(ast.parse(source)) or "").replace("\n  ", " ")
    found: dict[str, str] = {}
    for line in CATEGORY_LINE.finditer(docstring):
        for column in VISIT_COLUMN.finditer(line.group("columns")):
            found[column.group("column")] = line.group("category")
    return found


def _keywords(call: ast.Call) -> dict[str | None, ast.expr]:
    return {k.arg: k.value for k in call.keywords}


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def violations(source: str) -> list[str]:
    body = ast.Module(body=[upgrade(ast.parse(source))], type_ignores=[])
    problems = []
    used = {
        node.func.attr
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    }
    if used - {"create_table", "create_index", "f"}:
        problems.append(f"operations other than creating the table: {sorted(used)}")
    tables = calls(body, "create_table")
    if [ast.literal_eval(t.args[0]) for t in tables] != ["visit"]:
        return [*problems, "not exactly one created table, visit"]
    [table] = tables
    columns: dict[str, ast.Call] = {}
    keys: list[ast.Call] = []
    for item in table.args[1:]:
        if not isinstance(item, ast.Call):
            problems.append(f"not a column or constraint: {ast.unparse(item)}")
            continue
        kind = ast.unparse(item.func)
        if kind == "sa.Column":
            columns[ast.literal_eval(item.args[0])] = item
        elif kind == "sa.ForeignKeyConstraint":
            keys.append(item)
    if set(columns) != set(COLUMNS):
        problems.append(f"columns: {sorted(columns)}")
    for name, column in columns.items():
        keywords = _keywords(column)
        if _is_true(keywords.get("nullable")) != (name in NULLABLE):
            problems.append(f"{name}: nullable is not {name in NULLABLE}")
        for key in DEFAULTS:
            if key in keywords:
                problems.append(f"{name}: {key}")
        text = ast.unparse(column)
        if ISSUED.search(text.replace("sa.Uuid()", "")):
            problems.append(f"{name}: a database-issued value")
        if name in INSTANTS and "DateTime(timezone=True)" not in text:
            problems.append(f"{name}: not an instant with its offset")
        if name == "id" and "sa.Uuid()" not in text:
            problems.append("id: not a UUID")
    references = [ast.unparse(k) for k in keys]
    if references != [r for r in references if "'customer_id'" in r and "'customer.id'" in r] or (
        len(references) != 1
    ):
        problems.append(f"foreign keys: {references}")
    for foreign in keys:
        for action in ("ondelete", "onupdate"):
            if action in _keywords(foreign):
                problems.append(f"foreign key: {action}")
    if re.search(r"timeout|now\(|SET |UPDATE |INSERT |DELETE ", ast.unparse(body), re.IGNORECASE):
        problems.append("a timeout, a clock or a row change in the revision")
    found = categories(source)
    for name, category in COLUMNS.items():
        if found.get(name) != category:
            problems.append(f"{name}: not categorised {category}")
    return problems


def test_k01_revision_0010_only_creates_the_visit_table_on_0009() -> None:
    source = revision().read_text(encoding="utf-8")
    assert violations(source) == []
    assert assigned(source, "revision") == ["0010"]
    assert assigned(source, "down_revision") == ["0009"]


def test_k01_contrast_a_planted_default_cascade_state_or_missing_category_is_found() -> None:
    source = revision().read_text(encoding="utf-8")
    identity = source.replace(
        'sa.Column("id", sa.Uuid(), nullable=False)',
        'sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)',
    )
    assert identity != source
    assert "id: server_default" in violations(identity)
    cascade = source.replace('["customer.id"],', '["customer.id"], ondelete="CASCADE",')
    assert cascade != source
    assert "foreign key: ondelete" in violations(cascade)
    stateful = source.replace(
        'sa.Column("own_address", sa.Text(), nullable=True),',
        'sa.Column("own_address", sa.Text(), nullable=True),\n'
        '        sa.Column("state", sa.Text(), nullable=False),',
    )
    assert stateful != source
    assert any(p.startswith("columns:") for p in violations(stateful))
    nullable_customer = source.replace(
        'sa.Column("customer_id", sa.Uuid(), nullable=False)',
        'sa.Column("customer_id", sa.Uuid(), nullable=True)',
    )
    assert nullable_customer != source
    assert "customer_id: nullable is not False" in violations(nullable_customer)
    naive = source.replace('"starts_at", sa.DateTime(timezone=True)', '"starts_at", sa.DateTime()')
    assert naive != source
    assert "starts_at: not an instant with its offset" in violations(naive)
    uncategorised = source.replace("`visit.own_address`", "`visit.own_adress`")
    assert uncategorised != source
    assert "own_address: not categorised PD-C2" in violations(uncategorised)
    altering = source.replace(
        "def upgrade() -> None:\n",
        'def upgrade() -> None:\n    op.add_column("customer", sa.Column("x", sa.Text()))\n',
    )
    assert any("other than creating" in p for p in violations(altering))
