"""EKO-1-11 checks on the migration lock, its timeouts and the shipped revision tree.

Each check returns the violations it finds, empty when the rule holds, so every one can be shown
failing on a planted input.
"""

import re
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

import yaml

LOCK_FIELD = "x-migration-advisory-lock"
LOCK_VARIABLE = "MIGRATION_ADVISORY_LOCK_KEY"
LOCK_HOLDERS = ("migrate", "backup")
LOCK_TIMEOUT_VARIABLE = "MIGRATION_LOCK_TIMEOUT_SECONDS"
STATEMENT_TIMEOUT_VARIABLE = "MIGRATION_STATEMENT_TIMEOUT_SECONDS"
TIMEOUTS = {LOCK_TIMEOUT_VARIABLE: "5", STATEMENT_TIMEOUT_VARIABLE: "30"}
VERSIONS_DIR = "backend/migrations/versions/"
TESTS_DIR = "backend/tests/"
SHIPPED_REVISIONS = {"0001", "0002", "0003"}
VARIANT_DIR = "/app/migrations/versions/"
TIMEOUT_SETTING = re.compile(r"lock_timeout|statement_timeout|transaction_timeout", re.IGNORECASE)


def _mapping(node: yaml.Node) -> dict[str, yaml.Node]:
    assert isinstance(node, yaml.MappingNode), node
    return {key.value: value for key, value in node.value}


def lock_key(compose_text: str) -> int:
    """The key recorded in the composition's top-level `x-migration-advisory-lock` field."""
    source: dict[str, Any] = yaml.safe_load(compose_text)
    return int(source[LOCK_FIELD])


def migrate_environment_node(compose_text: str) -> dict[str, yaml.Node]:
    root = yaml.compose(compose_text)
    assert root is not None
    return _migrate_environment(root)


def environment_key_line(compose_text: str, service: str, variable: str) -> int:
    """The 0-based line of `variable`'s key in `service`'s environment (an alias value's own
    position is its anchor's, so the key node is used)."""
    root = yaml.compose(compose_text)
    assert root is not None
    node = _mapping(_mapping(_mapping(root)["services"])[service])["environment"]
    assert isinstance(node, yaml.MappingNode)
    for key, _ in node.value:
        if key.value == variable:
            line: int = key.start_mark.line
            return line
    raise KeyError(variable)


def _migrate_environment(root: yaml.Node) -> dict[str, yaml.Node]:
    return _service_environment(root, "migrate")


def _service_environment(root: yaml.Node, service: str) -> dict[str, yaml.Node]:
    node = _mapping(_mapping(_mapping(root)["services"])[service])
    environment = node.get("environment")
    return {} if environment is None else _mapping(environment)


def lock_reference_violations(compose_text: str) -> list[str]:
    """`migrate`'s MIGRATION_ADVISORY_LOCK_KEY is the top-level field itself (a YAML alias)."""
    root = yaml.compose(compose_text)
    assert root is not None
    field = _mapping(root).get(LOCK_FIELD)
    if field is None:
        return [f"compose.yaml has no top-level {LOCK_FIELD}"]
    problems = []
    if not isinstance(field, yaml.ScalarNode) or not re.fullmatch(r"-?[1-9][0-9]*", field.value):
        problems.append(f"{LOCK_FIELD} is not a non-zero integer literal")
    # One composed tree: an alias is the very node of its anchor.
    value = _migrate_environment(root).get(LOCK_VARIABLE)
    if value is None:
        problems.append(f"migrate's environment has no {LOCK_VARIABLE}")
    elif value is not field:
        problems.append(f"migrate's {LOCK_VARIABLE} is not a reference to {LOCK_FIELD}")
    # EKO-1-14 (gate 1, developer stop 1 A): backup may receive the key, only as the same alias.
    backup = _service_environment(root, "backup").get(LOCK_VARIABLE)
    if backup is not None and backup is not field:
        problems.append(f"backup's {LOCK_VARIABLE} is not {LOCK_FIELD}")
    return problems


def backup_lock_reference_violations(compose_text: str) -> list[str]:
    """`backup` receives MIGRATION_ADVISORY_LOCK_KEY as the alias of the top-level field."""
    root = yaml.compose(compose_text)
    assert root is not None
    field = _mapping(root).get(LOCK_FIELD)
    value = _service_environment(root, "backup").get(LOCK_VARIABLE)
    if value is None:
        return [f"backup's environment has no {LOCK_VARIABLE}"]
    if field is None or value is not field:
        return [f"backup's {LOCK_VARIABLE} is not {LOCK_FIELD}"]
    return []


def files_holding(files: Mapping[str, str], value: int) -> list[str]:
    """Tracked files outside backend/tests/ whose text holds the number as a whole number."""
    number = re.compile(rf"(?<![0-9]){re.escape(str(value))}(?![0-9])")
    return sorted(
        path
        for path, text in files.items()
        if not path.startswith(TESTS_DIR) and number.search(text)
    )


def timeout_literal_violations(compose_text: str) -> list[str]:
    """Both timeouts are literals in migrate's environment, with no interpolation, 5 s and 30 s."""
    environment = migrate_environment_node(compose_text)
    problems = []
    for name, expected in TIMEOUTS.items():
        node = environment.get(name)
        if node is None:
            problems.append(f"migrate's environment has no {name}")
        elif not isinstance(node, yaml.ScalarNode) or "$" in node.value:
            problems.append(f"migrate's {name} is not a literal")
        elif node.value != expected:
            problems.append(f"migrate's {name} is {node.value!r}, not {expected!r}")
    return problems


def other_services_with_timeouts(rendered: dict[str, Any]) -> list[str]:
    """No service but migrate receives the timeouts; only migrate and backup receive the lock key.

    EKO-1-14 (gate 1, developer stop 1 A): backup takes the lock by reference; that it is the
    alias, not an equal literal, is lock_reference_violations' check on the source.
    """
    problems = []
    for name, service in (rendered.get("services") or {}).items():
        environment = service.get("environment") or {}
        for variable in TIMEOUTS:
            if name != "migrate" and variable in environment:
                problems.append(f"{name}: receives {variable}")
        if name not in LOCK_HOLDERS and LOCK_VARIABLE in environment:
            problems.append(f"{name}: receives {LOCK_VARIABLE}")
    return problems


def revision_timeout_violations(files: Mapping[str, str]) -> list[str]:
    """No revision of the real tree sets lock_timeout, statement_timeout or transaction_timeout."""
    return [
        f"{path}: sets {match.group(0)}"
        for path, text in sorted(files.items())
        if path.startswith(VERSIONS_DIR)
        for match in TIMEOUT_SETTING.finditer(text)
    ]


def two_integer_form(key: int) -> tuple[int, int]:
    """The same 64 bits as the two signed 32-bit keys of the two-`integer` lock functions."""

    def signed(value: int) -> int:
        return value - (1 << 32) if value >= 1 << 31 else value

    unsigned = key & ((1 << 64) - 1)
    return signed(unsigned >> 32), signed(unsigned & 0xFFFFFFFF)


def pg_locks_identity(key: int) -> tuple[int, int, int]:
    """(classid, objid, objsubid) pg_locks shows for the single-`bigint` form of `key`."""
    unsigned = key & ((1 << 64) - 1)
    return unsigned >> 32, unsigned & 0xFFFFFFFF, 1


def leaked_values(text: str, values: Iterable[str]) -> list[str]:
    """Which of the given configuration values (URL, host, role, password) appear in a log."""
    return sorted({value for value in values if value and value in text})


HISTORY_LINE = re.compile(r"^(?P<parent>\S+) -> (?P<revision>[^\s,]+)")


def history_edges(history_output: str) -> dict[str, str | None]:
    """revision -> parent from `alembic history`; `<base>` is no parent."""
    edges: dict[str, str | None] = {}
    for line in history_output.splitlines():
        match = HISTORY_LINE.match(line.strip())
        if match:
            parent = match.group("parent")
            edges[match.group("revision")] = None if parent == "<base>" else parent
    return edges


def shipped_tree_violations(
    edges: Mapping[str, str | None], version_files: Iterable[str]
) -> list[str]:
    """K-07: the tree is exactly {0001, 0002, 0003}, each on the one before, and only their three
    files ship."""
    problems = []
    if set(edges) != SHIPPED_REVISIONS:
        problems.append(f"revisions {sorted(edges)}, not {sorted(SHIPPED_REVISIONS)}")
    if edges.get("0003") != "0002":
        problems.append(f"0003's parent is {edges.get('0003')!r}, not '0002'")
    if edges.get("0002") != "0001":
        problems.append(f"0002's parent is {edges.get('0002')!r}, not '0001'")
    if edges.get("0001") is not None:
        problems.append(f"0001's parent is {edges.get('0001')!r}, not the base")
    python_files = sorted(name for name in version_files if name.endswith(".py"))
    if len(python_files) != len(SHIPPED_REVISIONS) or not all(
        any(name.startswith(revision + "_") for name in python_files)
        for revision in SHIPPED_REVISIONS
    ):
        problems.append(f"files under migrations/versions: {python_files}")
    return problems


def listing_violations(shipped: Mapping[str, str], variant: Mapping[str, str]) -> list[str]:
    """K-07: a variant's file listing is the shipped one plus files under migrations/versions/."""
    problems = []
    for path in sorted(set(shipped) - set(variant)):
        problems.append(f"removed: {path}")
    for path in sorted(set(shipped) & set(variant)):
        if shipped[path] != variant[path]:
            problems.append(f"changed: {path}")
    for path in sorted(set(variant) - set(shipped)):
        if PurePosixPath(path).parent != PurePosixPath(VARIANT_DIR):
            problems.append(f"added outside {VARIANT_DIR}: {path}")
    return problems


def version_location_violations(alembic_ini: str, rendered: dict[str, Any]) -> list[str]:
    """K-07: script_location is the fixed one; nothing adds a revision location."""
    problems = []
    locations = re.findall(r"^\s*script_location\s*=\s*(.+?)\s*$", alembic_ini, re.MULTILINE)
    if locations != ["%(here)s/migrations"]:
        problems.append(f"alembic.ini script_location {locations}")
    if re.search(r"version_locations", alembic_ini, re.IGNORECASE):
        problems.append("alembic.ini sets version_locations")
    for name, service in (rendered.get("services") or {}).items():
        environment = service.get("environment") or {}
        for variable, value in environment.items():
            if "version_locations" in f"{variable}={value}".lower():
                problems.append(f"{name}: {variable} sets version_locations")
        command = " ".join(str(part) for part in service.get("command") or [])
        if "version_locations" in command.lower() or "version-locations" in command.lower():
            problems.append(f"{name}: command sets version locations")
    return problems
