"""ADR-0003-C35 (addendum of EKO-3-01, section 2): every function under `backend/app/data/` that
reads or changes rows of an owned table takes a visibility scope as a required parameter with no
default, and no module outside `backend/app/data/` refers to an owned table.

A function refers to an owned table when its body names an owned model or table, or names a
module-level value or function of its own module that does; the closure is taken to a fixed
point, so a helper or a column tuple cannot launder the reference. Each check returns the
violations it finds, so a planted source shows it failing.
"""

import ast
import re
from collections.abc import Mapping

OWNED_MODELS = frozenset({"CustomerRow", "CustomerContactRow"})
OWNED_TABLES = frozenset({"customer", "customer_contact"})
SCOPE_TYPES = frozenset({"VisibilityScope", "OwnedBy", "AllRecords"})
SCOPE_PARAMETER = "scope"
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


def unscoped_functions(files: Mapping[str, str]) -> list[str]:
    """`path:function: reason` for every function under `data` that reaches an owned table
    without a required, typed scope parameter."""
    problems = []
    for path, text in sorted(files.items()):
        if not path.startswith(DATA_PREFIX) or not path.endswith(".py") or path == MODELS_MODULE:
            continue
        tree = ast.parse(text)
        tainted = _tainted(tree)
        for function in _functions(tree):
            if not _names(function) & tainted:
                continue
            reason = _scope_parameter(function)
            if reason is not None:
                problems.append(f"{path}:{function.name}: {reason}")
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
