"""EKO-1-34 (#192): where the two K-06 tests start the browser login, read from their source.

K-02 places the fix at one site: the settle wait is the statement right before the login in both
tests. K-03's runtime fault test calls `browser_login` itself, so a catch written around the call
in a K-06 test body cannot reach it; these checks read the two test functions and the helper and
fail on a catch, a suppression, a loop or a second navigation around the login.
"""

import ast
from pathlib import Path

import pytest

from tests.support.repo import REPO_ROOT

K06_MODULE = REPO_ROOT / "backend" / "tests" / "runtime" / "test_k06_frontend_replacement.py"
LOGIN_MODULE = REPO_ROOT / "backend" / "tests" / "runtime" / "eko201_login.py"
K06_TESTS = (
    "test_k06_open_spa_recovers_unloaded_lazy_chunk_after_frontend_replacement",
    "test_r01_two_consecutive_lazy_chunk_failures_stop_after_one_recovery",
)
LOGIN_CALL = "app.browser_login(page, fresh, username, password)"
SETTLE_CALL = "settle_host_network(fresh)"


def function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    matches = [node for node in found if node.name == name]
    assert len(matches) == 1, f"{path.name}: {len(matches)} functions named {name}"
    return matches[0]


def parents(root: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(root) for child in ast.iter_child_nodes(node)}


def login_statements(test: ast.FunctionDef) -> list[ast.Expr]:
    return [
        node
        for node in ast.walk(test)
        if isinstance(node, ast.Expr) and ast.unparse(node.value) == LOGIN_CALL
    ]


def enclosing(test: ast.FunctionDef, statement: ast.AST) -> list[ast.AST]:
    up = parents(test)
    chain = []
    node = statement
    while node in up:
        node = up[node]
        chain.append(node)
    return chain


def maskers(chain: list[ast.AST]) -> list[str]:
    found = []
    for node in chain:
        if isinstance(node, ast.Try | ast.TryStar) and node.handlers:
            found.append(f"try/except at line {node.lineno}")
        if isinstance(node, ast.With):
            for item in node.items:
                source = ast.unparse(item.context_expr)
                if "suppress" in source or "raises" in source:
                    found.append(f"with {source} at line {node.lineno}")
        if isinstance(node, ast.For | ast.While):
            found.append(f"loop at line {node.lineno}")
    return found


@pytest.mark.parametrize("name", K06_TESTS)
def test_eko134_k02_the_k06_test_settles_the_host_network_right_before_the_login(
    name: str,
) -> None:
    test = function(K06_MODULE, name)
    [login] = login_statements(test)
    block = next(
        body
        for node in ast.walk(test)
        for body in (getattr(node, "body", None), getattr(node, "finalbody", None))
        if isinstance(body, list) and login in body
    )
    before = block[block.index(login) - 1]
    assert isinstance(before, ast.Expr) and ast.unparse(before.value) == SETTLE_CALL, (
        f"{name}: the statement before the login is {ast.unparse(before)!r}"
    )


@pytest.mark.parametrize("name", K06_TESTS)
def test_eko134_k03_nothing_catches_suppresses_or_repeats_the_login_in_the_k06_test(
    name: str,
) -> None:
    test = function(K06_MODULE, name)
    logins = login_statements(test)
    assert len(logins) == 1, f"{name}: {len(logins)} login calls"
    assert maskers(enclosing(test, logins[0])) == []
    calls = [
        node
        for node in ast.walk(test)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "app.browser_login"
    ]
    assert len(calls) == 1, f"{name}: browser_login is called {len(calls)} times"


def test_eko134_k03_browser_login_navigates_once_and_catches_nothing() -> None:
    login = function(LOGIN_MODULE, "browser_login")
    gotos = [
        node
        for node in ast.walk(login)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("goto", "reload", "go_back", "go_forward")
    ]
    assert [ast.unparse(node.func) for node in gotos] == ["page.goto"]
    blocks = [
        node for node in ast.walk(login) if isinstance(node, ast.Try | ast.TryStar | ast.With)
    ]
    assert blocks == [], [f"line {node.lineno}" for node in blocks]
    loops = [node for node in ast.walk(login) if isinstance(node, ast.For | ast.While)]
    assert loops == [], [f"line {node.lineno}" for node in loops]
