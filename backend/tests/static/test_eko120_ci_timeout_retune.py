"""EKO-1-20 (#76), QA: the checks that compare every existing `ci.yml` job to its base let a job's
own `timeout-minutes` value be retuned (and the one comment line directly above it change), and
nothing else. Contrasts in the same job: any other key, a removed `timeout-minutes`, one added to a
job that had none, and a non-integer value are each still a changed job.

Both shapes of the check are exercised: the parsed one (release_workflow.ci_unchanged_violations,
EKO-1-15 K-07) on the live base, the pre-merge fixture and the merged base; and the text one
(test_eko119_k03_release_mode_ci.assert_existing_jobs_unchanged) on the live base and the merged
base. Only `timeout-minutes` is allowed; removing it is red because the job then falls back to the
runner's default bound, and adding it is red because it gives a job a bound it never had.

The bases are fixed pairs, never the live branch (EKO-1-23, #110): "live" is EKO-1-20's own pair
(PR #113: EKO_1_20_BASE, EKO_1_20_HEAD), "pre-merge" is the pre-EKO-1-15 fixture against
EKO-1-15's own head, "merged" is the live head against itself.
"""

import copy
import re
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.static.test_eko115_k07_unchanged_on_both_bases import base as fixed_base
from tests.static.test_eko115_k07_unchanged_on_both_bases import claim_head
from tests.static.test_eko115_k07_unchanged_on_both_bases import head as head_flow
from tests.static.test_eko119_k03_release_mode_ci import assert_existing_jobs_unchanged
from tests.static.test_k07_changeset import in_worktree
from tests.support import release_workflow as rw
from tests.support.fixed_pair import file_at

CI = ".github/workflows/ci.yml"
# PR #113 (EKO-1-20): 5f1b1a0's parents; its merge base is the first parent.
EKO_1_20_BASE = "32deb05d257610f80a45b890fec84d7d153d2f31"
EKO_1_20_HEAD = "b21e45aa80b8517ea20be09c87d5690069b92ae9"
Workflow = dict[Any, Any]
TIMEOUT = "timeout-minutes"
JOB = "runtime"
FLOW_BASES = ("live", "pre-merge", "merged")
TEXT_BASES = ("live", "merged")


def pair_text(commit: str) -> str:
    text = file_at(commit, CI)
    assert text is not None
    return text


def flow_base(which: str) -> Workflow:
    if which == "live":
        flow: Workflow = yaml.safe_load(pair_text(EKO_1_20_BASE))
        return flow
    return fixed_base(which)


def claim_flow(which: str) -> Workflow:
    """The head the retune claim is judged on: EKO-1-20's own head for "live"."""
    if which == "live":
        flow: Workflow = yaml.safe_load(pair_text(EKO_1_20_HEAD))
        return flow
    return claim_head(which)


def head_text() -> str:
    text = in_worktree(CI)
    assert text is not None
    return text


def claim_text(which: str) -> str:
    return pair_text(EKO_1_20_HEAD) if which == "live" else head_text()


def text_base(which: str) -> str:
    return pair_text(EKO_1_20_BASE) if which == "live" else head_text()


# Parsed workflow ---------------------------------------------------------------------------


def _set(key: str, value: Any, job: str = JOB) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][job][key] = value
        return changed

    return apply


def _drop(key: str, job: str = JOB) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        del changed["jobs"][job][key]
        return changed

    return apply


def _last_run(flow: Workflow) -> Workflow:
    changed = copy.deepcopy(flow)
    step = [s for s in changed["jobs"][JOB]["steps"] if "run" in s][-1]
    step["run"] = step["run"] + "\ntrue"
    return changed


def _step_timeout(flow: Workflow) -> Workflow:
    changed = copy.deepcopy(flow)
    changed["jobs"][JOB]["steps"][-1][TIMEOUT] = 5
    return changed


RETUNED: dict[str, Callable[[Workflow], Workflow]] = {
    "runtime-longer": _set(TIMEOUT, 90),
    "runtime-shorter": _set(TIMEOUT, 30),
    "backend-retuned": _set(TIMEOUT, 16, "backend"),
}
STILL_CHANGED: dict[str, Callable[[Workflow], Workflow]] = {
    "runs-on": _set("runs-on", "ubuntu-22.04"),
    "needs": _set("needs", ["changes", "images"]),
    "if": _set("if", "always()"),
    "permissions": _set("permissions", {"contents": "write", "packages": "read"}),
    "continue-on-error-added": _set("continue-on-error", True),
    "a-step-run": _last_run,
    "a-step-timeout": _step_timeout,
    "timeout-removed": _drop(TIMEOUT),
    "timeout-not-an-integer": _set(TIMEOUT, "${{ inputs.minutes }}"),
    "timeout-as-a-boolean": _set(TIMEOUT, True),
    "timeout-and-runs-on": lambda f: _set("runs-on", "self-hosted")(_set(TIMEOUT, 90)(f)),
}


@pytest.mark.parametrize("which", FLOW_BASES)
@pytest.mark.parametrize("case_id", sorted(RETUNED))
def test_eko120_qa_a_retuned_timeout_is_not_a_changed_job(which: str, case_id: str) -> None:
    assert rw.ci_unchanged_violations(flow_base(which), RETUNED[case_id](claim_flow(which))) == []


@pytest.mark.parametrize("which", FLOW_BASES)
@pytest.mark.parametrize("case_id", sorted(STILL_CHANGED))
def test_eko120_qa_contrast_any_other_change_to_the_job_fails(which: str, case_id: str) -> None:
    planted = STILL_CHANGED[case_id](claim_flow(which))
    assert rw.ci_unchanged_violations(flow_base(which), planted) != [], case_id


def test_eko120_qa_contrast_a_timeout_added_to_a_job_that_had_none_fails() -> None:
    head = head_flow()
    assert rw.ci_unchanged_violations(_drop(TIMEOUT)(head), head) != []


# Text of each job ---------------------------------------------------------------------------


def _in_job(old: str, new: str, job: str = JOB) -> Callable[[str], str]:
    """Replace the first `old` inside one job's block of the file, asserting it is there."""

    def apply(text: str) -> str:
        start = text.index(f"\n  {job}:\n") + 1
        following = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start:])
        end = start + following.start() if following else len(text)
        block = text[start:end]
        assert old in block, (job, old)
        return text[:start] + block.replace(old, new, 1) + text[end:]

    return apply


def _timeout_line(job: str = JOB, text: str | None = None) -> str:
    where = head_text() if text is None else text
    found = re.search(rf"\n  {job}:\n(?:    .*\n|\s*\n)*?(    {TIMEOUT}: \d+)\n", where)
    assert found is not None, job
    return found.group(1)


def _retimed(minutes: int, job: str = JOB) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return _in_job(_timeout_line(job, text), f"    {TIMEOUT}: {minutes}", job)(text)

    return apply


def _commented(comment: str, job: str = JOB) -> Callable[[str], str]:
    def apply(text: str) -> str:
        line = _timeout_line(job, text)
        return _in_job(line, f"    # {comment}\n{line}", job)(text)

    return apply


def _comment_above_replaced(text: str) -> str:
    """The comment line directly above the runtime timeout, whatever the head holds there."""
    line = _timeout_line(text=text)
    lines = text.split("\n")
    index = lines.index(line, lines.index(f"  {JOB}:"))
    if lines[index - 1].startswith("    #"):
        lines[index - 1] = "    # another reason for the bound"
    else:
        lines.insert(index, "    # another reason for the bound")
    return "\n".join(lines)


def _timeout_dropped(text: str) -> str:
    """The runtime timeout line gone together with the comment line directly above it, so the
    key's presence is the only difference (an orphan comment would be red on its own)."""
    line = _timeout_line(text=text)
    lines = text.split("\n")
    index = lines.index(line, lines.index(f"  {JOB}:"))
    first = index - 1 if lines[index - 1].startswith("    #") else index
    return "\n".join(lines[:first] + lines[index + 1 :])


TEXT_RETUNED: dict[str, Callable[[str], str]] = {
    "runtime-value": _retimed(90),
    "backend-value": _retimed(16, "backend"),
    "runtime-comment-above-replaced": _comment_above_replaced,
    "backend-value-and-a-comment-above": lambda t: _retimed(16, "backend")(
        _commented("why", "backend")(t)
    ),
}
TEXT_STILL_CHANGED: dict[str, Callable[[str], str]] = {
    "runs-on": _in_job("    runs-on: ubuntu-latest", "    runs-on: ubuntu-22.04"),
    "needs": _in_job("    needs: changes", "    needs: [changes, images]"),
    "name": _in_job("    name: ", "    name: renamed "),
    "a-step-run": _in_job("        run: ", "        run: true && "),
    "a-comment-not-above-the-timeout": _in_job("    runs-on:", "    # planted\n    runs-on:"),
    "a-second-comment-above-the-timeout": lambda t: _commented("second")(_commented("first")(t)),
    "a-key-above-the-timeout": lambda t: _in_job(
        _timeout_line(text=t), f"    continue-on-error: true\n{_timeout_line(text=t)}"
    )(t),
    "timeout-removed": _timeout_dropped,
    "timeout-not-an-integer": lambda t: _in_job(
        _timeout_line(text=t), f"    {TIMEOUT}: ${{{{ inputs.minutes }}}}"
    )(t),
    "timeout-and-runs-on": lambda t: _in_job("    runs-on: ubuntu-latest", "    runs-on: x")(
        _retimed(90)(t)
    ),
}


@pytest.mark.parametrize("which", TEXT_BASES)
@pytest.mark.parametrize("case_id", sorted(TEXT_RETUNED))
def test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job(which: str, case_id: str) -> None:
    planted = TEXT_RETUNED[case_id](claim_text(which))
    assert planted != claim_text(which), case_id
    assert_existing_jobs_unchanged(text_base(which), planted)


@pytest.mark.parametrize("which", TEXT_BASES)
@pytest.mark.parametrize("case_id", sorted(TEXT_STILL_CHANGED))
def test_eko120_qa_contrast_any_other_line_change_fails(which: str, case_id: str) -> None:
    planted = TEXT_STILL_CHANGED[case_id](claim_text(which))
    assert planted != claim_text(which), case_id
    with pytest.raises(AssertionError):
        assert_existing_jobs_unchanged(text_base(which), planted)


def test_eko120_qa_contrast_a_timeout_line_added_to_a_job_that_had_none_fails() -> None:
    head = head_text()
    without = _timeout_dropped(head)
    with pytest.raises(AssertionError):
        assert_existing_jobs_unchanged(without, head)
