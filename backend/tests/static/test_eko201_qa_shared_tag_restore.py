"""EKO-2-01 QA (fix round 1, re-verification at 51d5342): QA-01's plant is always undone.

`test_qa01_prepare_replaces_a_stale_shared_tag_with_the_tree_build` tags a theme-less fixture over
the shared Keycloak tag. In build mode the tree build moves the tag back anyway, so dropping the
restore changes no outcome there; in release mode nothing rebuilds the tag, and without the
restore the host keeps the fixture under it after a passing run (seen in R18, and reproduced by
QA with the restore removed: the test passed and the tag was left on the fixture). No runtime
assertion notices that, so this pins the restore: the holder is read before the plant, and the
`finally` that follows the plant restores exactly that holder.
"""

import ast

from tests.support.repo import REPO_ROOT

QA01 = REPO_ROOT / "backend" / "tests" / "runtime" / "test_eko201_qa01_image_from_tree.py"
TEST = "test_qa01_prepare_replaces_a_stale_shared_tag_with_the_tree_build"


def restore_problems(source: str) -> list[str]:
    """What is missing for the plant in TEST to be undone whatever happens."""
    tree = ast.parse(source)
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == TEST]
    if len(functions) != 1:
        return [f"{TEST} not found once"]
    body = functions[0].body
    held_at = [
        i
        for i, stmt in enumerate(body)
        if isinstance(stmt, ast.Assign)
        and [t.id for t in stmt.targets if isinstance(t, ast.Name)] == ["held"]
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == "shared_tag_holder"
    ]
    tries = [i for i, stmt in enumerate(body) if isinstance(stmt, ast.Try) and stmt.finalbody]
    problems = []
    if not held_at:
        problems.append("the shared tag's holder is not read before the plant")
    if not tries:
        return [*problems, "the plant is not inside a try/finally"]
    statement = body[tries[-1]]
    assert isinstance(statement, ast.Try)
    if held_at and held_at[0] > tries[-1]:
        problems.append("the holder is read after the plant")
    restores = [
        stmt
        for stmt in statement.finalbody
        if isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == "restore_shared_tag"
        and [a.id for a in stmt.value.args if isinstance(a, ast.Name)] == ["held"]
    ]
    if not restores:
        problems.append("the finally does not call restore_shared_tag(held)")
    return problems


def test_qa_qa01_the_plant_is_undone_by_restoring_the_holder_read_before_it() -> None:
    assert restore_problems(QA01.read_text(encoding="utf-8")) == []


PLANTED = f"""
def {TEST}(tmp_path):
    held = shared_tag_holder()
    try:
        docker("tag", stale_tag, IMAGE)
    finally:
        {{finally_body}}
        subprocess.run(["docker", "rmi", "-f", stale_tag])
"""


def test_qa_contrast_a_finally_without_the_restore_is_named() -> None:
    assert restore_problems(PLANTED.format(finally_body="restore_shared_tag(held)")) == []
    assert restore_problems(PLANTED.format(finally_body="pass")) == [
        "the finally does not call restore_shared_tag(held)"
    ]


def test_qa_contrast_a_restore_to_something_else_is_named() -> None:
    assert restore_problems(PLANTED.format(finally_body="restore_shared_tag(None)")) == [
        "the finally does not call restore_shared_tag(held)"
    ]
