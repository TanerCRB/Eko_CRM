"""EKO-1-36 (#214) QA contrasts for K-05 as amended (A-09): `docs/PLAN.md` may change by added
lines only, and every other change to it fails, naming the path.

The developer's self-test plants added, edited and removed text lines. These cases cover the two
branches it leaves blind: a binary diff, which has no line counts and must fail closed (counted
as one removed line), and a deleted plan, which is not a modification and must fail as any
non-added path does. Plants live in a throwaway repository, as in the developer's self-test.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support import eko136_scope as scope
from tests.support.fixed_pair import Throwaway, add, delete

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

WITH_CHECKER = "be0c5f73bc5d2b479ce912a2e398ffa663f6dee9"
PLAN = "docs/PLAN.md"
CHANGE_UNDER_TEST = "backend/tests/static/test_eko136_planted.py"
Change = Callable[[Throwaway], None]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    return Throwaway(tmp_path / "repo", WITH_CHECKER, monkeypatch)


def line_prepended(line: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(PLAN)
        repo.put(PLAN, repo.blob(line + repo.text(PLAN)), mode)

    return change


def head_with(repo: Throwaway, plant: Change) -> str:
    under_test = repo.commit(WITH_CHECKER, add(CHANGE_UNDER_TEST))
    return repo.commit(under_test, plant)


def test_eko136_qa_k05_a_binary_plan_diff_fails_closed(repo: Throwaway) -> None:
    # Only a line is added, but a NUL in the first 8000 bytes makes Git diff the file as binary.
    head = head_with(repo, line_prepended("\0 planted\n"))
    assert scope.scope_violations(WITH_CHECKER, head) == [
        f"M {PLAN}: may change by added lines only; 1 line(s) removed or modified"
    ]


def test_eko136_qa_k05_contrast_the_same_line_without_the_nul_passes(repo: Throwaway) -> None:
    head = head_with(repo, line_prepended(" planted\n"))
    assert scope.scope_violations(WITH_CHECKER, head) == []


def test_eko136_qa_k05_a_deleted_plan_fails_as_a_path_that_was_not_added(repo: Throwaway) -> None:
    head = head_with(repo, delete(PLAN))
    assert scope.scope_violations(WITH_CHECKER, head) == [f"D {PLAN}: {scope.NOT_ADDED}"]
