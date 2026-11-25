"""EKO-3-06, ADR-0003-C39 (the gate-1 draft, section 2; A-6 A): under `backend/app/`, the operator
creation scope of `backend/app/domain/ownership.py` is reached only from `backend/app/seed.py`.

A module reaches it when it names the function in any form (an import, an alias, an attribute of
the `ownership` module) or imports the seed itself, which would carry it into that process. Run
on the repository's sources and on planted fixtures under `api/`, `auth/`, `main.py` and
`worker.py`, so the check can fail. The runtime half (each share stored under exactly its named
subject, the owner form refused before any write) is `tests/runtime/eko306/`.
"""

import ast

import pytest

from tests.static.test_eko301_adr0003_c35_owned_tables_scoped import app_sources

FUNCTION = "operator_creation_scope"
OWNERSHIP = "backend/app/domain/ownership.py"
SEED = "backend/app/seed.py"
SEED_MODULE = "app.seed"


def names_the_scope(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == FUNCTION:
            return True
        if isinstance(node, ast.Name) and node.id == FUNCTION:
            return True
        if isinstance(node, ast.Attribute) and node.attr == FUNCTION:
            return True
        if isinstance(node, ast.alias) and node.name.split(".")[-1] == FUNCTION:
            return True
    return False


def imports_the_seed(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(
            a.name == SEED_MODULE or a.name.startswith(SEED_MODULE + ".") for a in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == SEED_MODULE or (
                module == "app" and any(a.name == "seed" for a in node.names)
            ):
                return True
    return False


def reaching(sources: dict[str, str]) -> list[str]:
    """Every module under `backend/app/` but the two allowed that reaches the operator scope."""
    found = []
    for path, source in sorted(sources.items()):
        if not path.startswith("backend/app/") or path in {OWNERSHIP, SEED}:
            continue
        if names_the_scope(source) or imports_the_seed(source):
            found.append(path)
    return found


def test_c39_only_the_seed_reaches_the_operator_creation_scope() -> None:
    sources = app_sources()
    # Non-vacuity: the function exists where the decision puts it, and the seed does reach it.
    assert {p for p, s in sources.items() if names_the_scope(s)} == {OWNERSHIP, SEED}
    assert reaching(sources) == []


PLANTED = {
    "api-imports-it": (
        "backend/app/api/planted.py",
        "from app.domain.ownership import operator_creation_scope\n",
    ),
    "auth-aliases-it": (
        "backend/app/auth/planted.py",
        "from app.domain.ownership import operator_creation_scope as scope_of\n",
    ),
    "main-calls-it-through-the-module": (
        "backend/app/main.py",
        "from app.domain import ownership\n\n\n"
        "def f(s):\n    return ownership.operator_creation_scope(s)\n",
    ),
    "worker-imports-the-seed": ("backend/app/worker.py", "import app.seed\n"),
    "main-imports-from-the-seed": ("backend/app/main.py", "from app.seed import run\n"),
    "service-imports-the-seed-module": (
        "backend/app/services/planted.py",
        "from app import seed\n",
    ),
}


@pytest.mark.parametrize("variant", sorted(PLANTED))
def test_c39_contrast_a_planted_reach_outside_the_seed_fails(variant: str) -> None:
    path, text = PLANTED[variant]
    assert reaching({path: text}) == [path]


def test_c39_contrast_the_seed_and_the_ownership_module_themselves_pass() -> None:
    text = "from app.domain.ownership import operator_creation_scope\n"
    assert reaching({SEED: text, OWNERSHIP: f"def {FUNCTION}(s):\n    return s\n"}) == []
