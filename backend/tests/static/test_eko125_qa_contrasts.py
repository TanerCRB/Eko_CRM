"""EKO-1-25 (#133) QA contrasts for K-04 and K-05: one clause each that no existing plant isolates.

- K-04 mode parity: with the per-job comparison alone, a pair whose base already differs between
  the two modes and whose head keeps that difference passes; only the parity clause turns it red.
- K-05 comment-line rule: dropping only the comment line above a raised bound leaves the masked
  text and the parsed jobs equal; only the head-side "comment line directly above" clause sees it.
- K-05 exact bound line: `timeout-minutes: 360  # max` parses to the integer 360 and is masked
  like the bound line, so only the exact `BOUND_LINE` comparison sees it.

Each case has its contrast: the same input with the one changed element removed holds.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.static.test_eko125_k04_runtime_collection_unchanged import (
    BASES,
    CI,
    HEAD,
    RUNTIME_JOBS,
    Collected,
    collection_violations,
)
from tests.static.test_eko125_k05_runtime_jobs_change_only_their_bound import (
    BOUND_LINE,
    TIMEOUT,
    k05_violations,
)
from tests.support.fixed_pair import Throwaway

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

PARITY = "head: the two modes do not collect the same set"
ONE: Collected = {"tests/runtime/test_a.py::test_a": ("runtime",)}
TWO: Collected = {**ONE, "tests/runtime/test_b.py::test_b": ("runtime",)}


# K-04 mode parity ------------------------------------------------------------------------------


def test_eko125_qa_k04_modes_that_differ_at_both_sides_fail_on_parity_alone() -> None:
    differing = {RUNTIME_JOBS[0]: TWO, RUNTIME_JOBS[1]: ONE}
    assert collection_violations(differing, differing) == [PARITY]


def test_eko125_qa_k04_contrast_modes_that_agree_at_both_sides_hold() -> None:
    agreeing = {RUNTIME_JOBS[0]: TWO, RUNTIME_JOBS[1]: TWO}
    assert collection_violations(agreeing, agreeing) == []


# K-05 comment-line rule and exact bound line ---------------------------------------------------


def _comment_dropped(job: str) -> Callable[[Throwaway], None]:
    """Only the comment line directly above `job`'s bound line removed; the bound line stays."""

    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(CI)
        text = repo.text(CI)
        start = text.index(f"\n  {job}:\n")
        found = re.compile(rf"    #[^\n]*\n(?={BOUND_LINE}\n)").search(text, start)
        assert found is not None, job
        repo.put(CI, repo.blob(text[: found.start()] + text[found.end() :]), mode)

    return change


def _bound_line_suffixed(job: str, suffix: str) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(CI)
        text = repo.text(CI)
        start = text.index(f"\n  {job}:\n")
        at = text.index(f"\n{BOUND_LINE}\n", start) + 1
        end = at + len(BOUND_LINE)
        repo.put(CI, repo.blob(text[:end] + suffix + text[end:]), mode)

    return change


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    return Throwaway(tmp_path / "repo", HEAD, monkeypatch)


def test_eko125_qa_k05_the_comment_line_alone_dropped_fails_on_both_bases(
    throwaway: Throwaway,
) -> None:
    planted = throwaway.commit(HEAD, _comment_dropped("runtime-checked"))
    for base in BASES:
        found = k05_violations(base, planted)
        assert f"job runtime-checked: no comment line directly above {TIMEOUT}" in found, found


def test_eko125_qa_k05_a_trailing_comment_on_the_bound_line_fails_on_both_bases(
    throwaway: Throwaway,
) -> None:
    planted = throwaway.commit(HEAD, _bound_line_suffixed("runtime", "  # max"))
    expected = f"job runtime: '{BOUND_LINE.strip()}  # max' is not '{BOUND_LINE.strip()}'"
    for base in BASES:
        found = k05_violations(base, planted)
        assert found == [expected], found


def test_eko125_qa_k05_contrast_an_empty_suffix_holds(throwaway: Throwaway) -> None:
    planted = throwaway.commit(HEAD, _bound_line_suffixed("runtime", ""))
    found = k05_violations(HEAD, planted)
    assert found == [], found
