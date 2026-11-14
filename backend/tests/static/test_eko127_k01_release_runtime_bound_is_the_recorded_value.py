"""EKO-1-27 (#138) K-01: the `runtime` job of `release.yml` carries an explicit integer
`timeout-minutes` equal to the bound recorded at gate 1 (Clarifications C-1: 360 minutes,
GitHub's job maximum), strictly above the longest completed duration of the same suite recorded
on this task's tree (126.4 min, run 43043176502, PLAN.md EKO-1-25 Done row).

EKO-1-30 (#152) split this file's single value node into its two halves and separated the two
pairs the #138 record and a future retune live in. The LIVE pair — `BOUND`, `BOUND_LINE` — is
the bound a retune moves: the live value node guards the working tree against it, and EKO-1-27's
DoD ("a duration reaching the bound returns the value to gate 1") is the decision that may move
it. The RECORD pair — `RECORDED_BOUND`, `RECORDED_BOUND_LINE`, `RECORDED_RAISE` — is #138's
history: the pair-frozen k02/k03 guards and every pinned-head, base-contrast, simulated-head,
range, shape and control check in this file read only the record names, and a retune must not
touch them. Each line constant derives from its value through `bound_line_of` (K-05): a value
move cannot leave its line behind, which is the desync R-01 counted as 13 bare plant deaths.
`test_eko130_retune_simulation_separates_live_from_record.py` drives this separation with a
simulated bound and reddens exactly the must-move nodes below.

The classification (EKO-1-23 style, one line per `test_eko127_*` node of this tree; the
simulation enforces agreement node for node). Carriers are compact: node ids drop the common
`test_eko127_` prefix, `move` means must-move-on-retune and `pinned` means must-stay-pinned
(the lint line limit; the simulation restores and checks the full ids). For the retune task:
move the live `BOUND` (with `release.yml` in the same change set — the line follows by
derivation); only a `move` verdict may change, and a `pinned` verdict that reddens is a
defect in the retune, not history to re-pin.

- k01_release_runtime_bound_is_the_live_value: move
- k01_release_runtime_bound_is_the_recorded_value: pinned
- k01_the_recorded_bound_is_within_the_recorded_range: pinned
- k01_contrast_the_base_before_the_raise_fails: pinned
- k01_a_simulated_head_with_only_the_raise_carries_the_bound: pinned
- k01_each_planted_value_shape_is_rejected[above-the-platform-maximum]: pinned
- k01_each_planted_value_shape_is_rejected[boolean]: pinned
- k01_each_planted_value_shape_is_rejected[bound-plus-one]: pinned
- k01_each_planted_value_shape_is_rejected[float]: pinned
- k01_each_planted_value_shape_is_rejected[key-dropped]: pinned
- k01_each_planted_value_shape_is_rejected[negative]: pinned
- k01_each_planted_value_shape_is_rejected[quoted]: pinned
- k01_each_planted_value_shape_is_rejected[restored-to-60]: pinned
- k01_each_planted_value_shape_is_rejected[zero]: pinned
- k01_the_control_one_element_swap_to_the_recorded_bound_passes: pinned
- k01_the_line_constants_derive_from_their_bound_values: pinned
- k02_release_yml_changes_only_the_runtime_bound: pinned
- k02_contrast_the_later_base_against_itself_holds: pinned
- k02_contrast_the_base_before_the_raise_fails: pinned
- k02_a_pair_commit_missing_from_the_object_store_raises: pinned
- k02_a_simulated_head_with_only_the_raise_passes: pinned
- k02_each_plant_alone_fails_on_both_bases[a-second-bound-line-in-another-job]: pinned
- k02_each_plant_alone_fails_on_both_bases[a-second-bound-line-in-the-runtime-job]: pinned
- k02_each_plant_alone_fails_on_both_bases[a-second-comment-line-above-the-bound]: pinned
- k02_each_plant_alone_fails_on_both_bases[a-step-level-timeout]: pinned
- k02_each_plant_alone_fails_on_both_bases[a-trailing-inline-comment-on-the-bound-line]: pinned
- k02_each_plant_alone_fails_on_both_bases[bound-moved-to-another-job]: pinned
- k02_each_plant_alone_fails_on_both_bases[bound-restored-to-60]: pinned
- k02_each_plant_alone_fails_on_both_bases[continue-on-error-beside-the-bound]: pinned
- k02_each_plant_alone_fails_on_both_bases[keys-reordered-in-the-runtime-job]: pinned
- k02_each_plant_alone_fails_on_both_bases[or-true-on-the-run-line]: pinned
- k02_each_plant_alone_fails_on_both_bases[publish-bound-retuned]: pinned
- k02_each_plant_alone_fails_on_both_bases[runtime-needs-changed]: pinned
- k02_each_plant_alone_fails_on_both_bases[runtime-permissions-widened]: pinned
- k02_each_plant_alone_fails_on_both_bases[the-concurrency-group-edited]: pinned
- k02_each_plant_alone_fails_on_both_bases[value-361]: pinned
- k02_each_plant_alone_fails_on_both_bases[value-boolean]: pinned
- k02_each_plant_alone_fails_on_both_bases[value-float]: pinned
- k02_each_plant_alone_fails_on_both_bases[value-negative]: pinned
- k02_each_plant_alone_fails_on_both_bases[value-quoted]: pinned
- k02_each_plant_alone_fails_on_both_bases[value-zero]: pinned
- k02_each_plant_alone_fails_on_both_bases[whitespace-only-in-another-job]: pinned
- k02_the_verdict_ignores_the_live_base: pinned
- k03_no_other_workflow_or_runtime_test_changes: pinned
- k03_contrast_the_base_against_itself_holds: pinned
- k03_a_pair_commit_missing_from_the_object_store_raises: pinned
- k03_a_simulated_head_with_only_the_raise_passes: pinned
- k03_each_plant_alone_fails_on_both_bases[a-runtime-test-added]: pinned
- k03_each_plant_alone_fails_on_both_bases[a-runtime-test-file-edited]: pinned
- k03_each_plant_alone_fails_on_both_bases[ci-runtime-checked-bound-retuned]: pinned
- k03_each_plant_alone_fails_on_both_bases[label-guard-workflow-changed]: pinned
- k03_each_plant_alone_fails_on_both_bases[runtime-conftest-changed]: pinned
- k03_each_plant_alone_fails_on_both_bases[support-helper-added]: pinned
- k03_each_plant_alone_fails_on_both_bases[support-helper-edited]: pinned
- k03_each_plant_alone_fails_on_both_bases[the-pyproject-changed]: pinned

The pair: BASE is the task branch's fork point (`git merge-base origin/main HEAD` at task
start); HEAD is the checkpoint commit carrying the raise and these guards, stamped by the
supervisor once it exists (`git rev-parse`), never typed by hand. The simulated-head node
below proves, before the stamp, what the pinned-head side of the record value node reports
after it.
"""

from collections.abc import Callable
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
OLD_BOUND_LINE = f"    {TIMEOUT}: 60"
# The one provenance comment line C-3 (gate 1) requires directly above the bound: it cites the
# Issue and gate decision, the completed durations the bound rests on, and the platform maximum.
PROVENANCE = (
    "    # EKO-1-27 (#138): the release-mode runtime suite ran 126.4/122.6 min (run "
    "43043176502) and 125.3/115.3 min (run 43074142146), above the old 60; 360 is GitHub's "
    "job maximum, chosen at gate 1 (C-1)."
)


def bound_line_of(bound: int) -> str:
    """The bound line's text for `bound` — the single source (EKO-1-30 K-05): value and line
    cannot drift apart, because every line is this derivation of a value. #138's original
    literal is what R-01's 13 bare plant deaths grew from."""
    return f"    {TIMEOUT}: {bound}"


# The LIVE pair: the bound a retune moves (EKO-1-27 DoD; gate 1 of #152, C-1 = G-1 A). The
# live value node guards the working tree against `BOUND`; nothing pair-frozen reads these.
BOUND = 360
BOUND_LINE = bound_line_of(BOUND)


def raise_for(bound: int) -> Callable[[Throwaway], None]:
    """#138's raise applied at `bound`: the bound line replaced by the provenance comment and
    `bound_line_of(bound)`, nothing else — a move of the value carries line and raise text
    with it (K-05 paired application). K-02's simulated head applies exactly this to the
    pinned base; k02's claim node then requires the stamped head's bound line to equal
    `bound_line_of(RECORDED_BOUND)` and a comment line directly above it — the comment itself
    is enforced only for existence, indent, `#` prefix and position (C-3 as recorded at gate
    1 of #138), never for content."""
    return edit(RELEASE, f"{OLD_BOUND_LINE}\n", f"{PROVENANCE}\n{bound_line_of(bound)}\n")


# The RECORD pair: #138's history, read by the pair-frozen k02/k03 and this file's record
# nodes. A retune never moves these values (gate 1 of #152, C-1); the recorded 360 below is
# the value k02's claim node compares the pinned head to.
RECORDED_BOUND = 360
RECORDED_BOUND_LINE = bound_line_of(RECORDED_BOUND)
RECORDED_RAISE = raise_for(RECORDED_BOUND)

# PR for EKO-1-27: the task branch's fork point, and the checkpoint commit carrying the raised
# bound and these guards. The base was taken with `git merge-base origin/main HEAD` at task
# start; the head SHA cannot exist before the checkpoint commit is made.
BASE = "044e957891d5f1d256d1b9ae8e62d4f7e3f02061"
# STAMP-EKO-1-27: the supervisor replaces the value of this one line with the full SHA of the
# checkpoint commit (`git rev-parse HEAD` after it exists). Until stamped, every node that
# reads the pinned head fails with the missing-commit error; nothing else on this line changes.
HEAD = "bb5f8554aa7911a626d1f428d973df067a38faff"
BASES = (BASE, HEAD)

Workflow = dict[Any, Any]


def bound_violations(text: str, bound: int = BOUND) -> list[str]:
    """The runtime job's bound as the explicit integer `bound`, or why the file does not carry
    it: a missing job, a missing key, a non-integer value (booleans and strings are values the
    runner will not read as minutes), or an integer that is not `bound`. The default is the
    live pair; the record nodes pass `RECORDED_BOUND` at their call sites (Q-A A, gate 1 of
    #152 — parameterized, so a retune drives the live half without a monkeypatch that
    from-imports would defeat)."""
    flow: Workflow = yaml.safe_load(text)
    job = (flow.get("jobs") or {}).get(RUNTIME)
    if not isinstance(job, dict):
        return [f"no {RUNTIME} job"]
    if TIMEOUT not in job:
        return [f"{TIMEOUT} is not explicit on the {RUNTIME} job"]
    value = job[TIMEOUT]
    if type(value) is not int:
        return [f"{TIMEOUT} is {value!r}, not an integer"]
    if value != bound:
        return [f"{TIMEOUT} is {value}, not {bound}"]
    return []


def live_text() -> str:
    """The workflow file as this tree holds it — the live half of the invariant."""
    return (REPO_ROOT / RELEASE).read_text(encoding="utf-8")


def pinned_text(commit: str) -> str:
    """The workflow file as `commit` stores it; a missing commit raises (`fixed_pair`)."""
    text = file_at(commit, RELEASE)
    assert text is not None, f"{RELEASE} missing at {commit[:12]}"
    return text


def test_eko127_k01_release_runtime_bound_is_the_live_value(bound: int = BOUND) -> None:
    """The live half of the value node (EKO-1-30 fact 6): the working tree's bound must equal
    the live pair's value. This is the one node a retune's verdict moves — with `release.yml`
    and `BOUND` changed in the same gate-approved set."""
    assert bound_violations(live_text(), bound) == []


def test_eko127_k01_release_runtime_bound_is_the_recorded_value() -> None:
    """The record half: the pinned head must carry the bound #138 recorded, `RECORDED_BOUND`
    — history that a later retune never re-pins (the live invariant's own claim moved to
    `..._is_the_live_value`, and stays guarding the working tree on `main`)."""
    assert bound_violations(pinned_text(HEAD), RECORDED_BOUND) == []


def test_eko127_k01_the_recorded_bound_is_within_the_recorded_range() -> None:
    """127 is one above the longest completed duration of the same suite recorded on this
    tree (126.4 min, run 43043176502); 360 is the platform job maximum ci.yml's C-5 comment
    records. The floor rests on the recorded history only — this task's fresh PR-run duration
    is K-04's human observation and is never read here (the criterion that reads CI runs
    cannot be a test in the tree). EKO-1-30: the range pins the RECORDED bound — a retune
    moves the live value, not the recorded range's history."""
    assert 127 <= RECORDED_BOUND <= 360


def test_eko127_k01_contrast_the_base_before_the_raise_fails() -> None:
    """The guard is not empty: at the pinned base the job still holds 60, so the same check
    reports the miss instead of passing."""
    found = bound_violations(pinned_text(BASE), RECORDED_BOUND)
    assert f"{TIMEOUT} is 60, not {RECORDED_BOUND}" in found


def test_eko127_k01_a_simulated_head_with_only_the_raise_carries_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the pinned-head side of the record value node reports once the checkpoint SHA is
    stamped: a throwaway head — the pinned base with `RECORDED_RAISE` applied and nothing
    else — carries `RECORDED_BOUND`. A record node (gate 1 of #152, K-01 edges): the raise
    text is #138's, so a retune never moves this check."""
    repo = Throwaway(tmp_path / "repo", BASE, monkeypatch)
    simulated = repo.commit(BASE, RECORDED_RAISE)
    assert bound_violations(pinned_text(simulated), RECORDED_BOUND) == []


def test_eko127_k01_the_line_constants_derive_from_their_bound_values() -> None:
    """K-05's named equality node: both pairs are structurally coupled — each line constant
    is the derivation helper applied to its value, so a value move cannot leave a literalized
    line behind. The raise closure's coupling to the record pair is read in the wiring (the
    `raise_for(RECORDED_BOUND)` definition, checked by test_eko130) and exercised by
    `test_eko130_k05_...`, which moves the pair through the helpers. The plant tables
    deliberately embed recorded literals ("360", "361", "99999") — those are judged against
    the record machinery and must not derive (K-05 edges); this node couples the pairs, not
    the plants."""
    assert BOUND_LINE == bound_line_of(BOUND)
    assert RECORDED_BOUND_LINE == bound_line_of(RECORDED_BOUND)


DROPPED = object()
# Value-shape plants on the pinned base's bound line, mirroring test_eko125_k05's table: each
# must be rejected, reporting exactly the wrong, mistyped or missing value it is. The
# fragments are #138's record: they name RECORDED_BOUND, the value the head must carry.
SHAPES: dict[str, tuple[str | object, str]] = {
    "restored-to-60": ("60", f"{TIMEOUT} is 60, not {RECORDED_BOUND}"),
    "quoted": ('"360"', f"{TIMEOUT} is '360', not an integer"),
    "boolean": ("true", f"{TIMEOUT} is True, not an integer"),
    "float": ("360.0", f"{TIMEOUT} is 360.0, not an integer"),
    "zero": ("0", f"{TIMEOUT} is 0, not {RECORDED_BOUND}"),
    "negative": ("-1", f"{TIMEOUT} is -1, not {RECORDED_BOUND}"),
    "bound-plus-one": ("361", f"{TIMEOUT} is 361, not {RECORDED_BOUND}"),
    "above-the-platform-maximum": ("99999", f"{TIMEOUT} is 99999, not {RECORDED_BOUND}"),
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
    assert fragment in bound_violations(_planted_base_bound(raw), RECORDED_BOUND)


def test_eko127_k01_the_control_one_element_swap_to_the_recorded_bound_passes() -> None:
    """Contrast to the shape table: with only the bound line reading the recorded value, the
    same check on the same base text passes — one element changed, verdict reversed."""
    assert bound_violations(_planted_base_bound("360"), RECORDED_BOUND) == []
