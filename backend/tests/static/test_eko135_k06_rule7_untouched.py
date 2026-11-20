"""EKO-1-35 K-06: the check adds no reference across `backend/` and `frontend/`, and rule 7's
guard (`cross_tree_references` and its test) is not narrowed.

The guard's files are judged against the change set's base (`test_k07_changeset`); once the
checker is in the base, a later change set is not this one. The contrasts never read the base.
"""

from tests.static.test_k07_changeset import at_base, in_worktree
from tests.support import source_checks as sc

CHECKER = "backend/tests/support/frontend_contract.py"
GUARD = (
    "backend/tests/support/source_checks.py",
    "backend/tests/static/test_eko110_k04_frontend_sources.py",
)
Texts = dict[str, str | None]


def is_eko135_change_set() -> bool:
    return at_base(CHECKER) is None


def guard_changes(base: Texts, head: Texts) -> list[str]:
    """Each guard file whose text differs from the base, or that is missing on either side."""
    return [path for path in GUARD if base.get(path) is None or base.get(path) != head.get(path)]


def test_eko135_k06_rule7_guard_is_identical_to_the_base() -> None:
    if not is_eko135_change_set():
        return
    base = {path: at_base(path) for path in GUARD}
    assert None not in base.values()
    assert guard_changes(base, {path: in_worktree(path) for path in GUARD}) == []


def test_eko135_k06_no_reference_across_the_trees_at_the_head() -> None:
    assert sc.cross_tree_references(sc.repository_sources()) == []


def test_eko135_k06_a_frontend_file_naming_a_backend_path_fails() -> None:
    files = dict(sc.repository_sources())
    files["frontend/src/api/contract.ts"] = '// "../backend/app/api/auth.py"\nexport {};\n'
    assert sc.cross_tree_references(files) != []


def test_eko135_k06_an_edited_or_missing_guard_file_fails() -> None:
    text = 'FRONTEND_TO_BACKEND = _tree_reference("backend", "\'\\"`")\n'
    base: Texts = {GUARD[0]: text, GUARD[1]: "def test(): ...\n"}
    exempted: Texts = {**base, GUARD[0]: text + "EXEMPT = ('frontend/src/api/',)\n"}
    assert guard_changes(base, exempted) == [GUARD[0]]
    assert guard_changes(base, {**base, GUARD[1]: None}) == [GUARD[1]]
    assert guard_changes(base, dict(base)) == []
