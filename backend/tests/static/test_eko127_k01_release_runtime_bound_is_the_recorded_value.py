"""EKO-1-27 (#138) K-01: the `runtime` job of `release.yml` carries an explicit integer
`timeout-minutes` equal to the bound recorded at gate 1 (Clarifications C-1: 360 minutes,
GitHub's job maximum), strictly above the longest completed duration of the same suite recorded
on this task's tree (126.4 min, run 43043176502, PLAN.md EKO-1-25 Done row).

The value node is a live invariant (EKO-1-23 classification): it keeps guarding `BOUND` on
`main` after the merge, so any later retune must move this constant through its own gate
decision. The same check is made on the task's pinned head, read through Git objects only —
never `$CHANGESET_BASE`, `origin/main`, `HEAD` or the working tree (house rule since EKO-1-23) —
and the pinned base, still at 60, is the emptiness contrast: the check reports the wrong value
instead of passing silently.

The pair: BASE is the task branch's fork point (`git merge-base origin/main HEAD` at task
start); HEAD is the checkpoint commit carrying the raise and these guards, stamped by the
supervisor once it exists (`git rev-parse`), never typed by hand. The simulated-head node
below proves, before the stamp, what the pinned-head side of the value node reports after it.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support import workflow_checks as wc
from tests.support.fixed_pair import Throwaway, edit, file_at
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

RELEASE = ".github/workflows/release.yml"
RUNTIME = "runtime"
TIMEOUT = wc.TIMEOUT_KEY
BOUND_LINE = f"    {TIMEOUT}: 360"
OLD_BOUND_LINE = f"    {TIMEOUT}: 60"
# The one provenance comment line C-3 (gate 1) requires directly above the bound: it cites the
# Issue and gate decision, the completed durations the bound rests on, and the platform maximum.
PROVENANCE = (
    "    # EKO-1-27 (#138): the release-mode runtime suite ran 126.4/122.6 min (run "
    "43043176502) and 125.3/115.3 min (run 43074142146), above the old 60; 360 is GitHub's "
    "job maximum, chosen at gate 1 (C-1)."
)
# The raise itself: the bound line replaced by the provenance comment and `BOUND_LINE`, nothing
# else. K-02's simulated head applies exactly this to the pinned base; K-02's claim node then
# requires the stamped head to carry the same bytes.
RAISE = edit(RELEASE, f"{OLD_BOUND_LINE}\n", f"{PROVENANCE}\n{BOUND_LINE}\n")

# PR for EKO-1-27: the task branch's fork point, and the checkpoint commit carrying the raised
# bound and these guards. The base was taken with `git merge-base origin/main HEAD` at task
# start; the head SHA cannot exist before the checkpoint commit is made.
BASE = "044e957891d5f1d256d1b9ae8e62d4f7e3f02061"
# STAMP-EKO-1-27: the supervisor replaces the value of this one line with the full SHA of the
# checkpoint commit (`git rev-parse HEAD` after it exists). Until stamped, every node that
# reads the pinned head fails with the missing-commit error; nothing else on this line changes.
HEAD = "0" * 40
BASES = (BASE, HEAD)

# Gate 1 of #138 recorded the bound as Clarifications C-1: 360 minutes, matching ci.yml's two
# runtime jobs (EKO-1-25 C-5). Copied from the Issue's line, the way test_eko125_k05 copied 360.
BOUND = 360
Workflow = dict[Any, Any]


def bound_violations(text: str) -> list[str]:
    """The runtime job's bound as the explicit integer `BOUND`, or why the file does not carry
    it: a missing job, a missing key, a non-integer value (booleans and strings are values the
    runner will not read as minutes), or an integer that is not `BOUND`."""
    flow: Workflow = yaml.safe_load(text)
    job = (flow.get("jobs") or {}).get(RUNTIME)
    if not isinstance(job, dict):
        return [f"no {RUNTIME} job"]
    if TIMEOUT not in job:
        return [f"{TIMEOUT} is not explicit on the {RUNTIME} job"]
    value = job[TIMEOUT]
    if type(value) is not int:
        return [f"{TIMEOUT} is {value!r}, not an integer"]
    if value != BOUND:
        return [f"{TIMEOUT} is {value}, not {BOUND}"]
    return []


def live_text() -> str:
    """The workflow file as this tree holds it — the live half of the invariant."""
    return (REPO_ROOT / RELEASE).read_text(encoding="utf-8")


def pinned_text(commit: str) -> str:
    """The workflow file as `commit` stores it; a missing commit raises (`fixed_pair`)."""
    text = file_at(commit, RELEASE)
    assert text is not None, f"{RELEASE} missing at {commit[:12]}"
    return text


def test_eko127_k01_release_runtime_bound_is_the_recorded_value() -> None:
    assert bound_violations(live_text()) == []
    assert bound_violations(pinned_text(HEAD)) == []


def test_eko127_k01_the_recorded_bound_is_within_the_recorded_range() -> None:
    """127 is one above the longest completed duration of the same suite recorded on this
    tree (126.4 min, run 43043176502); 360 is the platform job maximum ci.yml's C-5 comment
    records. The floor rests on the recorded history only — this task's fresh PR-run duration
    is K-04's human observation and is never read here (the criterion that reads CI runs
    cannot be a test in the tree)."""
    assert 127 <= BOUND <= 360


def test_eko127_k01_contrast_the_base_before_the_raise_fails() -> None:
    """The guard is not empty: at the pinned base the job still holds 60, so the same check
    reports the miss instead of passing."""
    assert f"{TIMEOUT} is 60, not {BOUND}" in bound_violations(pinned_text(BASE))


def test_eko127_k01_a_simulated_head_with_only_the_raise_carries_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the pinned-head side of the value node reports once the checkpoint SHA is stamped:
    a throwaway head — the pinned base with `RAISE` applied and nothing else — carries BOUND."""
    repo = Throwaway(tmp_path / "repo", BASE, monkeypatch)
    simulated = repo.commit(BASE, RAISE)
    assert bound_violations(pinned_text(simulated)) == []


DROPPED = object()
# Value-shape plants on the pinned base's bound line, mirroring test_eko125_k05's table: each
# must be rejected, reporting exactly the wrong, mistyped or missing value it is.
SHAPES: dict[str, tuple[str | object, str]] = {
    "restored-to-60": ("60", f"{TIMEOUT} is 60, not {BOUND}"),
    "quoted": ('"360"', f"{TIMEOUT} is '360', not an integer"),
    "boolean": ("true", f"{TIMEOUT} is True, not an integer"),
    "float": ("360.0", f"{TIMEOUT} is 360.0, not an integer"),
    "zero": ("0", f"{TIMEOUT} is 0, not {BOUND}"),
    "negative": ("-1", f"{TIMEOUT} is -1, not {BOUND}"),
    "bound-plus-one": ("361", f"{TIMEOUT} is 361, not {BOUND}"),
    "above-the-platform-maximum": ("99999", f"{TIMEOUT} is 99999, not {BOUND}"),
    "key-dropped": (DROPPED, f"{TIMEOUT} is not explicit on the {RUNTIME} job"),
}


def _planted_base_bound(raw: str | object) -> str:
    """The pinned base's text with the runtime job's bound line replaced by `raw` (or removed
    for `DROPPED`); the base has exactly one such line, the job's own 60."""
    lines = pinned_text(BASE).split("\n")
    [at] = [i for i, line in enumerate(lines) if line == OLD_BOUND_LINE]
    if raw is DROPPED:
        return "\n".join(lines[:at] + lines[at + 1 :])
    assert isinstance(raw, str)
    return "\n".join(lines[:at] + [f"    {TIMEOUT}: {raw}"] + lines[at + 1 :])


@pytest.mark.parametrize("case", sorted(SHAPES))
def test_eko127_k01_each_planted_value_shape_is_rejected(case: str) -> None:
    raw, fragment = SHAPES[case]
    assert fragment in bound_violations(_planted_base_bound(raw))


def test_eko127_k01_the_control_one_element_swap_to_the_recorded_bound_passes() -> None:
    """Contrast to the shape table: with only the bound line reading the recorded value, the
    same check on the same base text passes — one element changed, verdict reversed."""
    assert bound_violations(_planted_base_bound("360")) == []
