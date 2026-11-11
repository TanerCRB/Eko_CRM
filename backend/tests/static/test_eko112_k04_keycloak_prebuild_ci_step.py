"""EKO-1-12 K-04 (fix round 3, 2026-11-11): the release-mode job of `ci.yml` builds the keycloak
composition image before the K-04 snapshot, and the freeze checks (EKO-1-15 K-07, EKO-1-19 K-03,
EKO-1-20) tolerate exactly this one step — on the EKO-1-15 F-1 precedent: the step is listed as an
exact dict (rw.CI_KEYCLOAK_PREBUILD_STEP) and as the exact block of its own file lines
(wc.CI_KEYCLOAK_PREBUILD_LINES), dropped once from each side of the comparison.

Neither base is read from the live branch: a fixture must not follow the PR base, or the allowance
would claim to be proven inert after the merge. The pre-merge base is the head's `ci.yml` with the
step dropped, the merged base is the head's own file, which is what the base holds once merged
(the shape of test_eko115_k07_unchanged_on_both_bases.py). A second copy of the step, any mutation
of its text, a foreign step in the same job and the step in another job stay red against either
base; dropping the step altogether is red on the release-mode ordering check, not on the freeze
(which is inert by design — the ordering rule is what pins the step into the file).
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.static.test_eko119_k03_release_mode_ci import (
    CI,
    _prebuild_after_snapshot,
    assert_existing_jobs_unchanged,
    release,
)
from tests.static.test_k07_changeset import in_worktree
from tests.support import release_mode_ci as rm
from tests.support import release_workflow as rw
from tests.support import workflow_checks as wc

Workflow = dict[Any, Any]
Step = dict[str, Any]
BASES = ("pre-merge", "merged")
BLOCK = "\n".join(wc.CI_KEYCLOAK_PREBUILD_LINES)


def head_text() -> str:
    text = in_worktree(CI)
    assert text is not None
    return text


def head_flow() -> Workflow:
    flow: Workflow = yaml.safe_load(head_text())
    return flow


def without_step(flow: Workflow) -> Workflow:
    """The flow with one exact copy of the pre-build step dropped from the release-mode job."""
    changed = copy.deepcopy(flow)
    steps = changed["jobs"][rw.RELEASE_MODE_CI_JOB]["steps"]
    assert rw.CI_KEYCLOAK_PREBUILD_STEP in steps, "the head holds the step"
    steps.remove(rw.CI_KEYCLOAK_PREBUILD_STEP)
    return changed


def base_flow(which: str) -> Workflow:
    return head_flow() if which == "merged" else without_step(head_flow())


def base_text(which: str) -> str:
    if which == "merged":
        return head_text()
    masked = wc.keycloak_prebuild_lines_masked(head_text())
    assert masked != head_text(), "the head holds the exact block"
    return masked


# The head's ci.yml: the step is there, once, in its place ------------------------------------


def test_eko112_k04_ci_yml_holds_the_step_once_between_install_and_the_snapshot() -> None:
    flow = head_flow()
    steps = flow["jobs"][rw.RELEASE_MODE_CI_JOB]["steps"]
    assert steps.count(rw.CI_KEYCLOAK_PREBUILD_STEP) == 1
    install_at = rm._step(flow, rm.RELEASE_MODE_JOB, "uv sync --locked")[0]
    prebuild_at = steps.index(rw.CI_KEYCLOAK_PREBUILD_STEP)
    snapshot_at = rm._step(flow, rm.RELEASE_MODE_JOB, rm.SNAPSHOT)[0]
    assert install_at < prebuild_at < snapshot_at
    assert head_text().count(BLOCK) == 1


def test_eko112_the_listed_step_and_the_masked_block_are_the_same_step() -> None:
    # the trailing newline: in ci.yml the step's block scalar is followed by the snapshot step,
    # so its run value ends with one line break (clip chomping keeps it, never two)
    parsed: Workflow = yaml.safe_load(f"steps:\n{BLOCK}\n")
    assert parsed["steps"] == [rw.CI_KEYCLOAK_PREBUILD_STEP]
    assert rw.RELEASE_MODE_CI_JOB == rm.RELEASE_MODE_JOB


# The ordering rule (release-mode check): present, before the snapshot -------------------------


def test_eko112_release_mode_check_accepts_the_ci_yml_and_fails_the_step_moved() -> None:
    flow = head_flow()
    assert rm.release_mode_violations(flow, release()) == [], "the head's ci.yml first"
    planted = copy.deepcopy(flow)
    _prebuild_after_snapshot(planted)
    assert rm.release_mode_violations(planted, release()) != []


def test_eko112_release_mode_check_fails_when_the_step_is_dropped() -> None:
    assert rm.release_mode_violations(without_step(head_flow()), release()) != []


# The freeze tolerance, both shapes and both bases ----------------------------------------------


@pytest.mark.parametrize("which", BASES)
def test_eko112_k07_allows_the_step_on_both_bases(which: str) -> None:
    assert rw.ci_unchanged_violations(base_flow(which), head_flow()) == []


@pytest.mark.parametrize("which", BASES)
def test_eko112_k03_job_text_allows_the_step_on_both_bases(which: str) -> None:
    assert_existing_jobs_unchanged(base_text(which), head_text())


def _insert(flow: Workflow, job: str, index: int, step: Step) -> Workflow:
    changed = copy.deepcopy(flow)
    changed["jobs"][job]["steps"].insert(index, copy.deepcopy(step))
    return changed


def _edit(flow: Workflow, mutate: Callable[[Step], Step]) -> Workflow:
    changed = copy.deepcopy(flow)
    steps = changed["jobs"][rw.RELEASE_MODE_CI_JOB]["steps"]
    index = steps.index(rw.CI_KEYCLOAK_PREBUILD_STEP)
    steps[index] = mutate(dict(steps[index]))
    return changed


LISTED = rw.CI_KEYCLOAK_PREBUILD_STEP
FREEZE_PLANTS: dict[str, Callable[[Workflow], Workflow]] = {
    "second-copy": lambda f: _insert(
        f, rw.RELEASE_MODE_CI_JOB, len(f["jobs"][rw.RELEASE_MODE_CI_JOB]["steps"]), LISTED
    ),
    "step-in-another-job": lambda f: _insert(f, rm.BUILD_MODE_JOB, 1, LISTED),
    "run-wrong-service": lambda f: _edit(
        f, lambda s: {**s, "run": str(s["run"]).replace("build keycloak", "build postgres")}
    ),
    "run-precondition-dropped": lambda f: _edit(
        f, lambda s: {**s, "run": str(s["run"]).split("\n", 1)[1]}
    ),
    "shell-dropped": lambda f: _edit(f, lambda s: {k: v for k, v in s.items() if k != "shell"}),
    "env-added": lambda f: _edit(f, lambda s: {**s, "env": {"EKO_KEYCLOAK_PREBUILD": "1"}}),
    "a-foreign-step-in-the-same-job": lambda f: _insert(
        f, rw.RELEASE_MODE_CI_JOB, 4, {"name": "planted", "run": "true"}
    ),
}


@pytest.mark.parametrize("which", BASES)
@pytest.mark.parametrize("case_id", sorted(FREEZE_PLANTS))
def test_eko112_freeze_fails_on_a_mutation_of_the_step_on_both_bases(
    which: str, case_id: str
) -> None:
    planted = FREEZE_PLANTS[case_id](head_flow())
    assert rw.ci_unchanged_violations(base_flow(which), planted) != [], case_id


def _second_copy(text: str) -> str:
    assert text.count(BLOCK) == 1
    return text.replace(BLOCK, f"{BLOCK}\n{BLOCK}", 1)


def _block_in_the_images_job(text: str) -> str:
    # placed so the block's lines are the job's only difference from the base — no added blank
    # line, or the plant would be red even under an over-broad masker that drops the block
    marker = "      - name: Image checks (ADR-0001-C5, ADR-0004-C9)\n"
    assert marker in text
    return text.replace(marker, BLOCK + "\n" + marker, 1)


TEXT_PLANTS: dict[str, Callable[[str], str]] = {
    "second-copy": _second_copy,
    "run-wrong-service": lambda t: t.replace(
        "--profile dev build keycloak", "--profile dev build postgres", 1
    ),
    "comment-dated-wrong": lambda t: t.replace(
        "# EKO-1-12 fix-round-3 (2026-11-11)", "# EKO-1-12 fix-round-9 (2026-12-31)", 1
    ),
    "block-in-another-job": _block_in_the_images_job,
}


@pytest.mark.parametrize("which", BASES)
@pytest.mark.parametrize("case_id", sorted(TEXT_PLANTS))
def test_eko112_job_text_fails_on_a_mutation_of_the_block_on_both_bases(
    which: str, case_id: str
) -> None:
    # the base is built outside raises(): its own missing-step assert must not pass as the
    # comparison's rejection
    base = base_text(which)
    planted = TEXT_PLANTS[case_id](head_text())
    assert planted != head_text(), case_id
    with pytest.raises(AssertionError):
        assert_existing_jobs_unchanged(base, planted)
