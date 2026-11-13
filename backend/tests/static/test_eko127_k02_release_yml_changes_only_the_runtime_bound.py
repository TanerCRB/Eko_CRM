"""EKO-1-27 (#138) K-02: on the task's pinned base/head pair, `release.yml` differs only in the
runtime job's bound line and the one provenance comment line directly above it (C-3, required).
Every other job (admission, backend, frontend, images, publish), every workflow-level key
(name, the tag-only trigger, top-level permissions, concurrency) and every other key of the
runtime job (name, needs, runs-on, its own permissions, outputs, steps including the byte-
identical pytest run line) is unchanged, and no failure masking (continue-on-error, `|| true`,
a step-level timeout) is added.

Judged in both forms, as test_eko125_k05_runtime_jobs_change_only_their_bound.py does: parsed
(job-dict equality, `workflow_checks.failures_fail_the_run`) and text (whole-file byte equality
once the runtime job's bound line is masked and the one comment line directly above it dropped;
on the head side the bound line must read exactly `    timeout-minutes: 360` with a comment
line above it). The pair is read through Git objects only, never `$CHANGESET_BASE`,
`origin/main`, `HEAD` or the working tree. Plants live in a throwaway repository and are judged
against both bases (the pinned base and the pinned head), so the verdict does not depend on
which base the live branch has — and it stays inert after the merge (EKO-1-25 follow-up rule:
no fixture here reads the live PR base). Differences from EKO-1-25, per the Analyst's note:
one job in `release.yml` instead of two in `ci.yml`, and the base carries no comment above the
bound (line 181 is `runs-on:`), so only the head side must have it.
"""

import difflib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.test_eko120_ci_timeout_retune import EKO_1_20_BASE
from tests.static.test_eko125_k04_runtime_collection_unchanged import both, job_edit
from tests.static.test_eko127_k01_release_runtime_bound_is_the_recorded_value import (
    BASE,
    BASES,
    BOUND,
    BOUND_LINE,
    HEAD,
    RAISE,
    RELEASE,
    RUNTIME,
    TIMEOUT,
)
from tests.support import workflow_checks as wc
from tests.support.fixed_pair import ABSENT, Throwaway, edit, file_at

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

MASK = f"    {TIMEOUT}: {wc.TIMEOUT_MASK}"
JOB_HEADER = re.compile(r"  [A-Za-z0-9_-]+:")
RUN_LINE = '        run: uv run pytest -m "runtime or previous_release" tests/runtime -v'
STEP = "      - name: Runtime tests on the checked images\n"
Workflow = dict[Any, Any]


def _without_bound(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != TIMEOUT}


def parsed_violations(base: Workflow, head: Workflow) -> list[str]:
    """Every workflow-level key and every job must match across the pair except the runtime
    job's `timeout-minutes`, which must be the explicit integer `BOUND` on the head side."""
    problems: list[str] = []
    for key in sorted(set(base) | set(head), key=str):
        if key != "jobs" and base.get(key) != head.get(key):
            problems.append(f"workflow key {key!r} changed")
    base_jobs, head_jobs = base.get("jobs") or {}, head.get("jobs") or {}
    if list(base_jobs) != list(head_jobs):
        problems.append(f"jobs {list(base_jobs)} -> {list(head_jobs)}")
    for name, before in base_jobs.items():
        after = head_jobs.get(name)
        if name != RUNTIME:
            if after != before:
                problems.append(f"job {name} changed")
            continue
        if not isinstance(after, dict):
            problems.append(f"job {name} missing")
            continue
        if TIMEOUT not in after:
            problems.append(f"job {name}: no explicit {TIMEOUT}")
        elif type(after[TIMEOUT]) is not int or after[TIMEOUT] != BOUND:
            problems.append(f"job {name}: {TIMEOUT} is {after[TIMEOUT]!r}, not {BOUND}")
        rest_before, rest_after = _without_bound(before), _without_bound(after)
        for key in sorted(set(rest_before) | set(rest_after)):
            if rest_before.get(key) != rest_after.get(key):
                problems.append(f"job {name}: {key} changed")
        for step in after.get("steps") or []:
            if TIMEOUT in step:
                problems.append(f"job {name}: step {step.get('name')!r} has its own {TIMEOUT}")
    runtime = {
        name: head_jobs[name] for name in (RUNTIME,) if isinstance(head_jobs.get(name), dict)
    }
    return problems + wc.failures_fail_the_run({"jobs": runtime})


def _masked(text: str, side: str, problems: list[str]) -> list[str]:
    """The file's lines with the runtime job's bound line masked and the one comment line
    directly above it dropped. On the head side the bound line must read exactly `BOUND_LINE`,
    with a comment line directly above it (C-3 makes that line required, not merely allowed)."""
    lines = text.split("\n")
    dropped: set[int] = set()
    jobs = lines.index("jobs:") if "jobs:" in lines else len(lines)
    header = f"  {RUNTIME}:"
    if header not in lines[jobs:]:
        problems.append(f"{side}: no job {RUNTIME}")
        return lines
    start = lines.index(header, jobs)
    end = next(
        (i for i in range(start + 1, len(lines)) if JOB_HEADER.fullmatch(lines[i])), len(lines)
    )
    hits = [i for i in range(start + 1, end) if lines[i].startswith(f"    {TIMEOUT}:")]
    if len(hits) != 1:
        problems.append(f"{side}: job {RUNTIME} has {len(hits)} {TIMEOUT} lines, not one")
        return lines
    [at] = hits
    above = wc.JOB_COMMENT.fullmatch(lines[at - 1]) is not None
    if side == "head" and lines[at] != BOUND_LINE:
        problems.append(f"job {RUNTIME}: {lines[at].strip()!r} is not {BOUND_LINE.strip()!r}")
    if side == "head" and not above:
        problems.append(f"job {RUNTIME}: no comment line directly above {TIMEOUT}")
    lines[at] = MASK
    if above:
        dropped.add(at - 1)
    return [line for i, line in enumerate(lines) if i not in dropped]


def text_violations(base: str, head: str) -> list[str]:
    """Whole-file byte equality once the runtime job's bound (and its one comment line) are
    masked away; a difference anywhere else in the file — another job, indentation, key order —
    is a difference beyond the bound."""
    problems: list[str] = []
    before, after = _masked(base, "base", problems), _masked(head, "head", problems)
    if before != after:
        diff = difflib.unified_diff(before, after, "base", "head", lineterm="", n=0)
        shown = [line for line in diff if line[:1] in "+-" and line[:3] not in ("---", "+++")]
        problems.append(f"release.yml differs beyond the bound and its comment line: {shown[:6]}")
    return problems


def k02_violations(base: str, head: str) -> list[str]:
    """The K-02 claim between two commits, read through Git objects only; a missing commit
    raises (`fixed_pair.file_at`)."""
    base_text, head_text = file_at(base, RELEASE), file_at(head, RELEASE)
    if base_text is None or head_text is None:
        return [f"{RELEASE} missing"]
    problems = parsed_violations(yaml.safe_load(base_text), yaml.safe_load(head_text))
    return problems + text_violations(base_text, head_text)


# The claim on the pinned pair -----------------------------------------------------------------


def test_eko127_k02_release_yml_changes_only_the_runtime_bound() -> None:
    assert k02_violations(BASE, HEAD) == []


def test_eko127_k02_contrast_the_later_base_against_itself_holds() -> None:
    """Inert once merged: the head side judged against itself holds — the guard judges only
    this pair, never the live branch."""
    assert k02_violations(HEAD, HEAD) == []


def test_eko127_k02_contrast_the_base_before_the_raise_fails() -> None:
    """The check is not empty: judged on the pre-raise state (base against itself), both forms
    report it — 60 is not the bound, the bound line is not the exact text, and the required
    provenance comment line above it is missing."""
    found = k02_violations(BASE, BASE)
    assert f"job {RUNTIME}: {TIMEOUT} is 60, not {BOUND}" in found
    assert any(p.startswith(f"job {RUNTIME}: '{TIMEOUT}: 60' is not") for p in found)
    assert f"job {RUNTIME}: no comment line directly above {TIMEOUT}" in found


def test_eko127_k02_a_pair_commit_missing_from_the_object_store_raises() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        k02_violations(ABSENT, HEAD)


def test_eko127_k02_a_simulated_head_with_only_the_raise_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claim node's green side, provable before the checkpoint stamp: a throwaway head —
    the pinned base with `RAISE` applied and nothing else — passes both judgment forms."""
    repo = Throwaway(tmp_path / "repo", HEAD, monkeypatch)
    simulated = repo.commit(BASE, RAISE)
    assert k02_violations(BASE, simulated) == []


# Plants, each alone, on the pinned head; judged against both bases ----------------------------


def _bound(value: str) -> Callable[[Throwaway], None]:
    return job_edit(RELEASE, RUNTIME, f"{BOUND_LINE}\n", f"    {TIMEOUT}: {value}\n")


def _bound_dropped() -> Callable[[Throwaway], None]:
    """The bound line and the comment line above it gone, so only the key's presence differs."""

    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(RELEASE)
        text = repo.text(RELEASE)
        found = re.compile(rf"    #[^\n]*\n{re.escape(BOUND_LINE)}\n").search(text)
        assert found is not None
        repo.put(RELEASE, repo.blob(text[: found.start()] + text[found.end() :]), mode)

    return change


PLANTS: dict[str, tuple[Callable[[Throwaway], None], str]] = {
    "bound-moved-to-another-job": (
        both(
            _bound_dropped(),
            job_edit(RELEASE, "publish", "    timeout-minutes: 20\n", "    timeout-minutes: 360\n"),
        ),
        f"job {RUNTIME}: no explicit {TIMEOUT}",
    ),
    "bound-restored-to-60": (_bound("60"), f"{TIMEOUT} is 60, not {BOUND}"),
    "continue-on-error-beside-the-bound": (
        job_edit(
            RELEASE,
            RUNTIME,
            f"{BOUND_LINE}\n",
            f"{BOUND_LINE}\n    continue-on-error: true\n",
        ),
        f"{RUNTIME}: continue-on-error",
    ),
    "keys-reordered-in-the-runtime-job": (
        job_edit(
            RELEASE,
            RUNTIME,
            "    needs: [admission, images]\n    runs-on: ubuntu-latest\n",
            "    runs-on: ubuntu-latest\n    needs: [admission, images]\n",
        ),
        "differs beyond the bound",
    ),
    "or-true-on-the-run-line": (
        job_edit(RELEASE, RUNTIME, RUN_LINE, f"{RUN_LINE} || true"),
        "masks a failure",
    ),
    "publish-bound-retuned": (
        job_edit(RELEASE, "publish", "    timeout-minutes: 20\n", "    timeout-minutes: 21\n"),
        "job publish changed",
    ),
    "runtime-needs-changed": (
        job_edit(RELEASE, RUNTIME, "    needs: [admission, images]\n", "    needs: [images]\n"),
        f"job {RUNTIME}: needs changed",
    ),
    "runtime-permissions-widened": (
        job_edit(RELEASE, RUNTIME, "      packages: read\n", "      packages: write\n"),
        f"job {RUNTIME}: permissions changed",
    ),
    "a-second-bound-line-in-another-job": (
        job_edit(
            RELEASE,
            "publish",
            "    timeout-minutes: 20\n",
            "    timeout-minutes: 20\n    timeout-minutes: 360\n",
        ),
        "job publish changed",
    ),
    "a-second-bound-line-in-the-runtime-job": (
        job_edit(RELEASE, RUNTIME, f"{BOUND_LINE}\n", f"{BOUND_LINE}\n{BOUND_LINE}\n"),
        "has 2 timeout-minutes lines, not one",
    ),
    "a-second-comment-line-above-the-bound": (
        job_edit(RELEASE, RUNTIME, f"{BOUND_LINE}\n", f"    # planted\n{BOUND_LINE}\n"),
        "differs beyond the bound",
    ),
    "a-step-level-timeout": (
        job_edit(RELEASE, RUNTIME, STEP, f"{STEP}        timeout-minutes: 300\n"),
        "has its own timeout-minutes",
    ),
    "a-trailing-inline-comment-on-the-bound-line": (
        job_edit(RELEASE, RUNTIME, f"{BOUND_LINE}\n", f"{BOUND_LINE} # planted\n"),
        "is not 'timeout-minutes: 360'",
    ),
    "the-concurrency-group-edited": (
        edit(
            RELEASE,
            "  group: release-${{ github.ref }}\n",
            "  group: release-runtime-${{ github.ref }}\n",
        ),
        "workflow key 'concurrency' changed",
    ),
    "value-361": (_bound("361"), f"{TIMEOUT} is 361, not {BOUND}"),
    "value-boolean": (_bound("true"), f"{TIMEOUT} is True, not {BOUND}"),
    "value-float": (_bound("360.0"), f"{TIMEOUT} is 360.0, not {BOUND}"),
    "value-negative": (_bound("-1"), f"{TIMEOUT} is -1, not {BOUND}"),
    "value-quoted": (_bound('"360"'), f"{TIMEOUT} is '360', not {BOUND}"),
    "value-zero": (_bound("0"), f"{TIMEOUT} is 0, not {BOUND}"),
    "whitespace-only-in-another-job": (
        edit(
            RELEASE,
            "    name: image builds and image checks\n",
            "    name:  image builds and image checks\n",
        ),
        "differs beyond the bound",
    ),
}


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    """Selected for every git call of the check; its origin/main is the pinned head."""
    return Throwaway(tmp_path / "repo", HEAD, monkeypatch)


@pytest.mark.parametrize("case", sorted(PLANTS))
def test_eko127_k02_each_plant_alone_fails_on_both_bases(case: str, throwaway: Throwaway) -> None:
    change, fragment = PLANTS[case]
    planted = throwaway.commit(HEAD, change)
    for base in BASES:
        found = k02_violations(base, planted)
        assert any(fragment in problem for problem in found), (case, base, found)


def test_eko127_k02_the_verdict_ignores_the_live_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository whose HEAD, origin/main and $CHANGESET_BASE are all something else."""
    repo = Throwaway(tmp_path / "repo", EKO_1_20_BASE, monkeypatch)
    repo.checkout_files(EKO_1_20_BASE, RELEASE)
    monkeypatch.setenv("CHANGESET_BASE", ABSENT)
    assert k02_violations(BASE, HEAD) == []
    planted = repo.commit(HEAD, PLANTS["bound-restored-to-60"][0])
    assert f"job {RUNTIME}: {TIMEOUT} is 60, not {BOUND}" in k02_violations(BASE, planted)
