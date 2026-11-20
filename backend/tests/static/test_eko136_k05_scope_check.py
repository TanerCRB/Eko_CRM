"""EKO-1-36 (#214) K-05: the scope check `tests.support.eko136_scope`, judged on planted pairs.

QA runs the check on the PR's own pair (`python -m tests.support.eko136_scope <base> <head>`, both
full SHAs recorded in the PR). Here each plant lives in a throwaway repository on top of a planted
change under test, and is judged on two bases: WITH_CHECKER, which is the plant's merge base
(red, naming the path), and a later main that already holds the plant (green: inert after merge).
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support import eko136_scope as scope
from tests.support.fixed_pair import ABSENT, Throwaway, add, delete, modify, rename

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

WITH_CHECKER = "be0c5f73bc5d2b479ce912a2e398ffa663f6dee9"
CHECKER = "backend/tests/support/frontend_contract.py"
K06 = "backend/tests/static/test_eko135_k06_rule7_untouched.py"
CONTRACT_TREE = "backend/tests/support/contract_tree.py"
OTHER_TEST = "backend/tests/static/test_eko123_already_inert.py"
ROW = "docs/cost-register/2026-11-19_EKO-1-35_analysis_analyst_1.json"
PLAN = "docs/PLAN.md"
Change = Callable[[Throwaway], None]


def replaced_once(path: str, old: str, new: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        if text.count(old) != 1:
            raise ValueError(f"{path}: {old!r} occurs {text.count(old)} times, not once")
        repo.put(path, repo.blob(text.replace(old, new)), mode)

    return change


def appended(path: str, lines: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        repo.put(path, repo.blob(repo.text(path) + lines), mode)

    return change


def line_endings_to_crlf(path: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        assert "\r\n" not in text, path
        repo.put(path, repo.blob(text.replace("\n", "\r\n")), mode)

    return change


def changes(*each: Change) -> Change:
    def change(repo: Throwaway) -> None:
        for one in each:
            one(repo)

    return change


def not_added(status: str, path: str) -> str:
    return f"{status} {path}: {scope.NOT_ADDED}"


def frozen(path: str) -> str:
    return f"{path}: not byte-identical to the base"


def plan_not_added_only(removed: int) -> str:
    return f"M {PLAN}: may change by added lines only; {removed} line(s) removed or modified"


def untouchable(path: str, prefix: str) -> str:
    return f"{path}: under {prefix}, which this change may not touch"


CHANGE_UNDER_TEST = changes(
    add("backend/tests/static/test_eko136_planted.py"),
    add("backend/tests/support/eko136_planted.py"),
    add("docs/cost-register/2026-11-20_EKO-1-36_planted.json"),
)
# Each plant on top of the change under test, and exactly what the check must say at its merge base.
PLANTS: dict[str, tuple[Change, list[str]]] = {
    "checker-one-line-edit": (
        replaced_once(CHECKER, '"additionalProperties"}', '"additionalProperties", "nullable"}'),
        [not_added("M", CHECKER), frozen(CHECKER)],
    ),
    "checker-whitespace-only": (
        replaced_once(
            CHECKER,
            'COMPONENT_REF = "#/components/schemas/"\n',
            'COMPONENT_REF = "#/components/schemas/" \n',
        ),
        [not_added("M", CHECKER), frozen(CHECKER)],
    ),
    "checker-line-endings-only": (
        line_endings_to_crlf(CHECKER),
        [not_added("M", CHECKER), frozen(CHECKER)],
    ),
    "gate-parameter-added": (
        replaced_once(
            K06,
            "def is_eko135_change_set() -> bool:",
            "def is_eko135_change_set(base: str | None = None) -> bool:",
        ),
        [not_added("M", K06), frozen(K06)],
    ),
    "frozen-helper-deleted": (
        delete(CONTRACT_TREE),
        [not_added("D", CONTRACT_TREE), frozen(CONTRACT_TREE)],
    ),
    "other-test-file-modified": (modify(OTHER_TEST), [not_added("M", OTHER_TEST)]),
    "existing-test-renamed": (
        rename(OTHER_TEST, "backend/tests/static/test_eko123_renamed.py"),
        [not_added("D", OTHER_TEST)],
    ),
    "frontend-file-added": (
        add("frontend/src/planted.ts"),
        [
            not_added("A", "frontend/src/planted.ts"),
            untouchable("frontend/src/planted.ts", "frontend/"),
        ],
    ),
    "backend-app-file-added": (
        add("backend/app/planted.py"),
        [
            not_added("A", "backend/app/planted.py"),
            untouchable("backend/app/planted.py", "backend/app/"),
        ],
    ),
    "migration-added": (
        add("backend/migrations/versions/planted.py"),
        [
            not_added("A", "backend/migrations/versions/planted.py"),
            untouchable("backend/migrations/versions/planted.py", "backend/migrations/"),
        ],
    ),
    "doc-added-outside-the-cost-register": (
        add("docs/planted.md"),
        [not_added("A", "docs/planted.md")],
    ),
    "cost-register-row-edited": (modify(ROW), [not_added("M", ROW)]),
    "plan-lines-added-only": (
        appended(PLAN, "\n- [ ] **EKO-9-99** — A planted reservation.\n"),
        [],
    ),
    "plan-line-edited": (
        replaced_once(PLAN, "## EKO-2 — Access\n", "## EKO-2 — Access (edited)\n"),
        [plan_not_added_only(1)],
    ),
    "plan-line-removed": (
        replaced_once(PLAN, "## EKO-2 — Access\n", ""),
        [plan_not_added_only(1)],
    ),
}


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    """Selected for every git call of the check; nothing is written to the real repository."""
    return Throwaway(tmp_path / "repo", WITH_CHECKER, monkeypatch)


def later_main(repo: Throwaway, holding: str) -> str:
    """A main after `holding` merged (fast-forward), with one unrelated commit on top."""
    return repo.commit(holding, add("docs/after.md"))


def test_eko136_k05_the_change_under_test_passes_at_its_merge_base_and_later(
    repo: Throwaway,
) -> None:
    head = repo.commit(WITH_CHECKER, CHANGE_UNDER_TEST)
    assert scope.scope_violations(WITH_CHECKER, head) == []
    assert scope.scope_violations(later_main(repo, head), head) == []


@pytest.mark.parametrize("case", sorted(PLANTS))
def test_eko136_k05_each_plant_fails_naming_its_path_and_is_inert_after_merge(
    case: str, repo: Throwaway
) -> None:
    plant, expected = PLANTS[case]
    head = repo.commit(repo.commit(WITH_CHECKER, CHANGE_UNDER_TEST), plant)
    assert scope.scope_violations(WITH_CHECKER, head) == expected
    assert scope.scope_violations(later_main(repo, head), head) == []


def test_eko136_k05_an_empty_difference_passes(repo: Throwaway) -> None:
    assert scope.scope_violations(WITH_CHECKER, WITH_CHECKER) == []


@pytest.mark.parametrize(
    "pair",
    [
        (WITH_CHECKER[:12], WITH_CHECKER),
        (WITH_CHECKER, WITH_CHECKER.upper()),
        ("HEAD", WITH_CHECKER),
    ],
    ids=["abbreviated", "upper-case", "a-ref"],
)
def test_eko136_k05_a_pair_that_is_not_two_full_shas_cannot_be_judged(
    pair: tuple[str, str], repo: Throwaway
) -> None:
    with pytest.raises(scope.CannotJudge):
        scope.scope_violations(*pair)
    assert scope.main(list(pair)) == 2


def test_eko136_k05_a_commit_missing_from_the_object_store_cannot_be_judged(
    repo: Throwaway,
) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        scope.scope_violations(WITH_CHECKER, ABSENT)
    assert scope.main([WITH_CHECKER, ABSENT]) == 2
    assert scope.main([WITH_CHECKER]) == 2


def test_eko136_k05_the_command_exits_1_naming_the_path_and_0_on_the_change_under_test(
    repo: Throwaway, capsys: pytest.CaptureFixture[str]
) -> None:
    head = repo.commit(WITH_CHECKER, CHANGE_UNDER_TEST)
    assert scope.main([WITH_CHECKER, head]) == 0
    planted = repo.commit(head, add("frontend/src/planted.ts"))
    assert scope.main([WITH_CHECKER, planted]) == 1
    assert "frontend/src/planted.ts" in capsys.readouterr().out
