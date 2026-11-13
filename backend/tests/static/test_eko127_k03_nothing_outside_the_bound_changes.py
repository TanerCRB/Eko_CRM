"""EKO-1-27 (#138) K-03: the change reaches nothing beyond the one bound — on the task's pinned
pair no path under `.github/workflows/` other than `release.yml` changes (`ci.yml` included:
its two runtime bounds stay 360 and its C-5 comment lines stay), nothing under
`backend/tests/runtime/` or `backend/tests/support/` changes, and neither
`backend/tests/conftest.py` nor `backend/pyproject.toml` changes. The release runtime job's
pytest run line is byte-identical per K-02 and every input collection depends on is frozen
here, so the job collects exactly the runtime suite it collected before: this carries DoD item
4's "the collected runtime tests are unchanged" statically (the Out-of-scope entry accepted
at gate 1).

Judged on the pair's changed-path closure (`git diff --name-only` between the pinned commits,
the `changed_paths()` pattern of test_eko125_k04_runtime_collection_unchanged.py) — a different
mechanism than K-02's content comparison, so each guard fails independently of the other. The
pair is read through Git objects only, never `$CHANGESET_BASE`, `origin/main`, `HEAD` or the
working tree. Task bookkeeping paths (docs/PLAN.md reservation, cost-register rows) lie outside
the frozen prefixes and do not trip the check — they are on the pair by design.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.static.test_eko125_k04_runtime_collection_unchanged import changed_paths, job_edit
from tests.static.test_eko127_k01_release_runtime_bound_is_the_recorded_value import (
    BASE,
    BASES,
    HEAD,
    RAISE,
    RELEASE,
)
from tests.support.fixed_pair import ABSENT, Throwaway, add, edit, modify

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

WORKFLOWS = ".github/workflows/"
RUNTIME_TESTS = "backend/tests/runtime/"
SUPPORT = "backend/tests/support/"
CONTEST = "backend/tests/conftest.py"  # created by no commit today; creating it on the pair trips
PYPROJECT = "backend/pyproject.toml"
CI = ".github/workflows/ci.yml"
EXPIRY = "backend/tests/runtime/test_eko112_k04_event_expiry.py"


def changed_violations(base: str, head: str) -> list[str]:
    """Every changed path in a frozen prefix, named; a missing commit raises (`changed_paths`)."""
    problems = [f"{p} changes" for p in changed_paths(base, head, WORKFLOWS) if p != RELEASE]
    problems += [f"{p} changes" for p in changed_paths(base, head, RUNTIME_TESTS)]
    problems += [f"{p} changes" for p in changed_paths(base, head, SUPPORT)]
    problems += [f"{p} changes" for p in changed_paths(base, head, CONTEST)]
    return problems + [f"{p} changes" for p in changed_paths(base, head, PYPROJECT)]


# The claim on the pinned pair -----------------------------------------------------------------


def test_eko127_k03_no_other_workflow_or_runtime_test_changes() -> None:
    assert changed_violations(BASE, HEAD) == []


def test_eko127_k03_contrast_the_base_against_itself_holds() -> None:
    """Inert once merged: the pair read on the same commit changes nothing."""
    assert changed_violations(BASE, BASE) == []


def test_eko127_k03_a_pair_commit_missing_from_the_object_store_raises() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        changed_violations(ABSENT, HEAD)


def test_eko127_k03_a_simulated_head_with_only_the_raise_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claim node's green side, provable before the checkpoint stamp: a throwaway head —
    the pinned base with `RAISE` applied and nothing else — changes exactly `release.yml`."""
    repo = Throwaway(tmp_path / "repo", HEAD, monkeypatch)
    simulated = repo.commit(BASE, RAISE)
    assert changed_violations(BASE, simulated) == []


# Plants, each alone, on the pinned head; judged against both bases ----------------------------

PLANTS: dict[str, tuple[Callable[[Throwaway], None], str]] = {
    "a-runtime-test-added": (
        add("backend/tests/runtime/test_planted_eko127.py"),
        "backend/tests/runtime/test_planted_eko127.py changes",
    ),
    "a-runtime-test-file-edited": (
        edit(EXPIRY, "EXPIRY_WAIT_SECONDS = 1500", "EXPIRY_WAIT_SECONDS = 1200"),
        f"{EXPIRY} changes",
    ),
    "ci-runtime-checked-bound-retuned": (
        job_edit(CI, "runtime-checked", "    timeout-minutes: 360\n", "    timeout-minutes: 359\n"),
        f"{CI} changes",
    ),
    "label-guard-workflow-changed": (
        modify(".github/workflows/label-guard.yml"),
        ".github/workflows/label-guard.yml changes",
    ),
    "runtime-conftest-changed": (
        modify("backend/tests/runtime/conftest.py"),
        "backend/tests/runtime/conftest.py changes",
    ),
    "support-helper-added": (
        add("backend/tests/support/planted_helper.py"),
        "backend/tests/support/planted_helper.py changes",
    ),
    "support-helper-edited": (
        modify("backend/tests/support/git_sandbox.py"),
        "backend/tests/support/git_sandbox.py changes",
    ),
    "the-pyproject-changed": (
        modify(PYPROJECT),
        f"{PYPROJECT} changes",
    ),
}


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    """Selected for every git call of the check; its origin/main is the pinned head."""
    return Throwaway(tmp_path / "repo", HEAD, monkeypatch)


@pytest.mark.parametrize("case", sorted(PLANTS))
def test_eko127_k03_each_plant_alone_fails_on_both_bases(case: str, throwaway: Throwaway) -> None:
    change, fragment = PLANTS[case]
    planted = throwaway.commit(HEAD, change)
    for base in BASES:
        found = changed_violations(base, planted)
        assert any(fragment in problem for problem in found), (case, base, found)
