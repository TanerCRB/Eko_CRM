"""ADR-0003-C35 (addendum of EKO-3-01, section 2; restated by the addendum of EKO-3-08): every
function under `backend/app/data/` that reads or changes rows of an owned table takes a visibility
scope as a required parameter with no default, or is on the closed system-read list held here,
and no module outside `backend/app/data/` refers to an owned table. A listed function returns no
column of an owned table and is reached from no module under `backend/app/api/` or
`backend/app/auth/`.

A function refers to an owned table when its body names an owned model or table, or names a
module-level value or function of its own module that does; the closure is taken to a fixed
point, so a helper or a column tuple cannot launder the reference. Each check returns the
violations it finds, so a planted source shows it failing.
"""

import ast
import re
from collections.abc import Mapping

# EKO-4-01 (ADR-0003-C42): the visit table is an owned table, its owner its own `owner_subject`.
OWNED_MODELS = frozenset({"CustomerRow", "CustomerContactRow", "VisitRow"})
OWNED_TABLES = frozenset({"customer", "customer_contact", "visit"})
SCOPE_TYPES = frozenset({"VisibilityScope", "OwnedBy", "AllRecords"})
SCOPE_PARAMETER = "scope"
# ADR-0003 addendum of EKO-3-08 (Q-2 A): the closed system-read list, `path:function`. Adding an
# entry is a gate-1 decision of the task that adds it, on the Architect's impact map.
SYSTEM_READS = frozenset({"backend/app/data/staff.py:delete_unreferenced_copies"})
DATA_PREFIX = "backend/app/data/"
# The model module defines the owned tables; it holds no function that reads or changes them.
MODELS_MODULE = "backend/app/data/models.py"

_TABLES = "|".join(sorted(OWNED_TABLES))
SQL_REFERENCE = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+\"?(?:" + _TABLES + r")\b", re.IGNORECASE
)
OUTSIDE_REFERENCES = (
    re.compile(r"\b(?:" + "|".join(sorted(OWNED_MODELS)) + r")\b"),
    re.compile(r"[\"'](?:" + _TABLES + r")[\"']"),
    SQL_REFERENCE,
)


def _names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value in OWNED_TABLES or SQL_REFERENCE.search(child.value):
                found.add("customer")
        elif isinstance(child, ast.alias):
            found.add((child.asname or child.name).rsplit(".", 1)[-1])
            found.add(child.name.rsplit(".", 1)[-1])
    return found


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _module_bindings(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level names and what they are bound to: assignments, functions and classes."""
    bound: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        bound[name.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                bound[node.target.id] = node.value
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound[node.name] = node
    return bound


def _tainted(tree: ast.Module) -> set[str]:
    """Owned names, and every module-level name or method whose definition reaches one."""
    tainted = set(OWNED_MODELS | OWNED_TABLES)
    bindings = _module_bindings(tree)
    methods = {
        f.name: f
        for c in tree.body
        if isinstance(c, ast.ClassDef)
        for f in c.body
        if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    candidates = {**methods, **bindings}
    changed = True
    while changed:
        changed = False
        for name, node in candidates.items():
            if name not in tainted and _names(node) & tainted:
                tainted.add(name)
                changed = True
    return tainted


def _scope_parameter(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Why the function's `scope` parameter does not qualify, or None when it does."""
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: dict[str, ast.expr | None] = dict.fromkeys(a.arg for a in positional)
    for argument, default in zip(positional[len(positional) - len(arguments.defaults) :],
                                 arguments.defaults, strict=True):  # fmt: skip
        defaults[argument.arg] = default
    for keyword, keyword_default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        defaults[keyword.arg] = keyword_default
    every = {a.arg: a for a in [*positional, *arguments.kwonlyargs]}
    scope = every.get(SCOPE_PARAMETER)
    if scope is None:
        return "no scope parameter"
    if defaults[SCOPE_PARAMETER] is not None:
        return "the scope parameter has a default"
    if scope.annotation is None or not _names(scope.annotation) & SCOPE_TYPES:
        return "the scope parameter is not typed as a visibility scope"
    return None


def unscoped_functions(
    files: Mapping[str, str], system_reads: frozenset[str] = SYSTEM_READS
) -> list[str]:
    """`path:function: reason` for every function under `data` that reaches an owned table
    without a required, typed scope parameter and is not on the system-read list."""
    problems = []
    for path, text in sorted(files.items()):
        if not path.startswith(DATA_PREFIX) or not path.endswith(".py") or path == MODELS_MODULE:
            continue
        tree = ast.parse(text)
        tainted = _tainted(tree)
        for function in _functions(tree):
            if not _names(function) & tainted:
                continue
            if f"{path}:{function.name}" in system_reads:
                continue
            reason = _scope_parameter(function)
            if reason is not None:
                problems.append(f"{path}:{function.name}: {reason}")
    return problems


# Calls whose arguments become the columns a statement returns.
COLUMN_CALLS = frozenset({"select", "returning", "add_columns", "with_only_columns", "column"})
LAYERS_THAT_MUST_NOT_REACH = ("backend/app/api/", "backend/app/auth/")


def _called(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _returned_columns(function: ast.FunctionDef | ast.AsyncFunctionDef, tainted: set[str]) -> str:
    """Why the listed function may return a column of an owned table, or "" when it does not."""
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and _called(node) in COLUMN_CALLS:
            arguments = [*node.args, *(k.value for k in node.keywords)]
            if any(_names(a) & tainted for a in arguments):
                return f"`{_called(node)}` names an owned table"
        elif isinstance(node, ast.Return) and node.value is not None:
            if _names(node.value) & tainted:
                return "it returns a value naming an owned table"
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_REFERENCE.search(node.value):
                return "raw SQL names an owned table"
    return ""


def _module_name(path: str) -> str:
    dotted = path.removeprefix("backend/").removesuffix(".py").removesuffix("/__init__")
    return dotted.replace("/", ".")


def _imported(tree: ast.Module) -> set[str]:
    """Every module an import statement may bind, `from a import b` read as `a` and `a.b`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def _names_function(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and name in (node.name.rsplit(".", 1)[-1], node.asname):
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.Name) and node.id == name:
            return True
    return False


def _reached(
    start: ast.Module, trees: Mapping[str, ast.Module], modules: Mapping[str, str]
) -> set[str]:
    """The paths of every application module `start` imports, directly or through others."""
    seen: set[str] = set()
    pending = [m for m in _imported(start) if m in modules]
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        pending += [m for m in _imported(trees[modules[module]]) if m in modules]
    return {modules[m] for m in seen}


def system_read_problems(
    files: Mapping[str, str], system_reads: frozenset[str] = SYSTEM_READS
) -> list[str]:
    """`path: reason` for a listed function that is missing, that may return a column of an
    owned table, or that a module under `backend/app/api/` or `backend/app/auth/` reaches: by
    naming it, or by importing, directly or through other modules, a module that names it."""
    problems = []
    trees = {
        path: ast.parse(text)
        for path, text in sorted(files.items())
        if path.startswith("backend/app/") and path.endswith(".py")
    }
    modules = {_module_name(path): path for path in trees}
    for entry in sorted(system_reads):
        path, _, name = entry.partition(":")
        if path not in trees:
            continue
        found = [f for f in _functions(trees[path]) if f.name == name]
        if not found:
            problems.append(f"{entry}: the listed function is not defined")
            continue
        tainted = _tainted(trees[path])
        for function in found:
            reason = _returned_columns(function, tainted)
            if reason:
                problems.append(f"{entry}: {reason}")
        holders = {p for p, tree in trees.items() if p != path and _names_function(tree, name)}
        for start, tree in trees.items():
            if not start.startswith(LAYERS_THAT_MUST_NOT_REACH):
                continue
            if start in holders:
                problems.append(f"{start}: names the system read {name}")
                continue
            through = sorted(_reached(tree, trees, modules) & holders)
            if through:
                problems.append(f"{start}: reaches the system read {name} through {through[0]}")
    return problems


def owned_functions(files: Mapping[str, str]) -> list[str]:
    """Every function under `data` that reaches an owned table: the check's non-vacuity."""
    found = []
    for path, text in sorted(files.items()):
        if not path.startswith(DATA_PREFIX) or not path.endswith(".py") or path == MODELS_MODULE:
            continue
        tree = ast.parse(text)
        tainted = _tainted(tree)
        found += [f"{path}:{f.name}" for f in _functions(tree) if _names(f) & tainted]
    return found


def outside_references(files: Mapping[str, str]) -> list[str]:
    """`path:line` for every reference to an owned model or table in `backend/app/` outside
    `backend/app/data/`."""
    problems = []
    for path, text in sorted(files.items()):
        if not path.startswith("backend/app/") or path.startswith(DATA_PREFIX):
            continue
        if not path.endswith(".py"):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in OUTSIDE_REFERENCES):
                problems.append(f"{path}:{number}")
    return problems


# ADR-0003-C36 (addendum of EKO-3-04, Q-4 A) ------------------------------------------------------

SCOPE_VALUES = frozenset({"OwnedBy", "AllRecords"})
OWNERSHIP_MODULE = "backend/app/domain/ownership.py"
TYPE_CHECKS = frozenset({"isinstance", "issubclass"})


def _annotations(tree: ast.Module) -> set[int]:
    """The ids of every node inside a type annotation."""
    roots: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            roots.append(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.returns:
            roots.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            roots.append(node.annotation)
    return {id(child) for root in roots for child in ast.walk(root)}


def _type_checked(tree: ast.Module) -> set[int]:
    """The ids of the class side of `isinstance`/`issubclass` and of a `case` class pattern."""
    roots: list[ast.AST] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in TYPE_CHECKS
            and len(node.args) == 2
        ):
            roots.append(node.args[1])
        elif isinstance(node, ast.MatchClass):
            roots.append(node.cls)
    return {id(child) for root in roots for child in ast.walk(root)}


def scope_constructions(
    files: Mapping[str, str], everywhere: bool = False
) -> list[tuple[str, int]]:
    """`(path, line)` for every use of `OwnedBy` or `AllRecords` under `backend/app/` that could
    build a scope value: a call, or the class handed on as a value (an alias, a default, a
    factory). A type annotation, an import and the class side of `isinstance` or of a `case`
    pattern only name the type. The ownership module itself is left out unless `everywhere`."""
    found = []
    for path, text in sorted(files.items()):
        if not path.startswith("backend/app/") or not path.endswith(".py"):
            continue
        if path == OWNERSHIP_MODULE and not everywhere:
            continue
        tree = ast.parse(text)
        aliases = set(SCOPE_VALUES)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                aliases |= {a.asname for a in node.names if a.name in SCOPE_VALUES and a.asname}
        named_only = _annotations(tree) | _type_checked(tree)
        for node in ast.walk(tree):
            if id(node) in named_only:
                continue
            if isinstance(node, ast.Name) and node.id in aliases and isinstance(node.ctx, ast.Load):
                found.append((path, node.lineno))
            elif isinstance(node, ast.Attribute) and node.attr in SCOPE_VALUES:
                found.append((path, node.lineno))
    return found
