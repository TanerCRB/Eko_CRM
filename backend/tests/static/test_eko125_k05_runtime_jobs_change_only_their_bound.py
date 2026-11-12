"""EKO-1-25 (#133) K-05: on the task's pinned pair, each `ci.yml` runtime job changes only in its
`timeout-minutes` (written explicitly, the integer 360 in both jobs) and the one comment line
directly above it. Nothing else in `ci.yml` changes, no other workflow file changes and nothing
under `backup/` changes.

Judged in both forms, as test_eko120_ci_timeout_retune.py does: parsed (every other job, every
workflow-level key and every other key of a runtime job equal; no `continue-on-error`, `|| true` or
step-level timeout) and text (the whole file byte-equal once each runtime job's bound line and the
one comment line above it are masked). The pair is read through Git objects only, never
`$CHANGESET_BASE`, `origin/main`, `HEAD` or the working tree. Plants live in a throwaway repository
and are judged against two bases (the pinned base and the pinned head).
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
from tests.static.test_eko125_k04_runtime_collection_unchanged import (
    BASE,
    BASES,
    CI,
    HEAD,
    RUN_LINE,
    RUNTIME_JOBS,
    changed_paths,
    job_edit,
)
from tests.support import workflow_checks as wc
from tests.support.fixed_pair import ABSENT, Throwaway, edit, file_at, modify

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

BOUND = 360
TIMEOUT = wc.TIMEOUT_KEY
BOUND_LINE = f"    {TIMEOUT}: {BOUND}"
MASK = f"    {TIMEOUT}: {wc.TIMEOUT_MASK}"
JOB_HEADER = re.compile(r"  [A-Za-z0-9_-]+:")
WORKFLOWS = ".github/workflows/"
RELEASE = ".github/workflows/release.yml"
BACKUP = "backup/"
Workflow = dict[Any, Any]


def _without_bound(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != TIMEOUT}


def parsed_violations(base: Workflow, head: Workflow) -> list[str]:
    problems = []
    for key in sorted(set(base) | set(head), key=str):
        if key != "jobs" and base.get(key) != head.get(key):
            problems.append(f"workflow key {key!r} changed")
    base_jobs, head_jobs = base.get("jobs") or {}, head.get("jobs") or {}
    if list(base_jobs) != list(head_jobs):
        problems.append(f"jobs {list(base_jobs)} -> {list(head_jobs)}")
    for name, before in base_jobs.items():
        after = head_jobs.get(name)
        if name not in RUNTIME_JOBS:
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
    runtime = {n: head_jobs[n] for n in RUNTIME_JOBS if isinstance(head_jobs.get(n), dict)}
    return problems + wc.failures_fail_the_run({"jobs": runtime})


def _masked(text: str, side: str, problems: list[str]) -> list[str]:
    """The file's lines with each runtime job's bound line masked and the one comment line
    directly above it dropped. On the head side the bound line must read exactly `BOUND_LINE`,
    with a comment line directly above it."""
    lines = text.split("\n")
    dropped: set[int] = set()
    jobs = lines.index("jobs:") if "jobs:" in lines else len(lines)
    for job in RUNTIME_JOBS:
        header = f"  {job}:"
        if header not in lines[jobs:]:
            problems.append(f"{side}: no job {job}")
            continue
        start = lines.index(header, jobs)
        end = next(
            (i for i in range(start + 1, len(lines)) if JOB_HEADER.fullmatch(lines[i])), len(lines)
        )
        hits = [i for i in range(start + 1, end) if lines[i].startswith(f"    {TIMEOUT}:")]
        if len(hits) != 1:
            problems.append(f"{side}: job {job} has {len(hits)} {TIMEOUT} lines, not one")
            continue
        [at] = hits
        above = wc.JOB_COMMENT.fullmatch(lines[at - 1]) is not None
        if side == "head" and lines[at] != BOUND_LINE:
            problems.append(f"job {job}: {lines[at].strip()!r} is not {BOUND_LINE.strip()!r}")
        if side == "head" and not above:
            problems.append(f"job {job}: no comment line directly above {TIMEOUT}")
        lines[at] = MASK
        if above:
            dropped.add(at - 1)
    return [line for i, line in enumerate(lines) if i not in dropped]


def text_violations(base: str, head: str) -> list[str]:
    problems: list[str] = []
    before, after = _masked(base, "base", problems), _masked(head, "head", problems)
    if before != after:
        diff = difflib.unified_diff(before, after, "base", "head", lineterm="", n=0)
        shown = [line for line in diff if line[:1] in "+-" and line[:3] not in ("---", "+++")]
        problems.append(f"ci.yml differs beyond the bound and its comment line: {shown[:6]}")
    return problems


def k05_violations(base: str, head: str) -> list[str]:
    base_text, head_text = file_at(base, CI), file_at(head, CI)
    if base_text is None or head_text is None:
        return [f"{CI} missing"]
    problems = parsed_violations(yaml.safe_load(base_text), yaml.safe_load(head_text))
    problems += text_violations(base_text, head_text)
    problems += [f"{p} changes" for p in changed_paths(base, head, WORKFLOWS) if p != CI]
    return problems + [f"{p} changes" for p in changed_paths(base, head, BACKUP)]


# The claim on the pinned pair -----------------------------------------------------------------


def test_eko125_k05_runtime_jobs_change_only_their_bound() -> None:
    assert k05_violations(BASE, HEAD) == []


def test_eko125_k05_contrast_the_later_base_against_itself_holds() -> None:
    assert k05_violations(HEAD, HEAD) == []


def test_eko125_k05_contrast_the_base_before_the_raise_fails() -> None:
    """The check is not empty: at the base both runtime jobs still hold 75."""
    found = k05_violations(BASE, BASE)
    for job in RUNTIME_JOBS:
        assert f"job {job}: {TIMEOUT} is 75, not {BOUND}" in found
    assert any(p.startswith("job runtime: 'timeout-minutes: 75' is not") for p in found)


def test_eko125_k05_a_pair_commit_missing_from_the_object_store_raises() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        k05_violations(ABSENT, HEAD)


# Plants, each alone, on the pinned head; judged against both bases ----------------------------


def _bound(job: str, value: str) -> Callable[[Throwaway], None]:
    return job_edit(CI, job, f"{BOUND_LINE}\n", f"    {TIMEOUT}: {value}\n")


def _bound_dropped(job: str) -> Callable[[Throwaway], None]:
    """The bound line and the comment line above it gone, so only the key's presence differs."""

    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(CI)
        text = repo.text(CI)
        start = text.index(f"\n  {job}:\n")
        found = re.compile(rf"    #[^\n]*\n{BOUND_LINE}\n").search(text, start)
        assert found is not None, job
        repo.put(CI, repo.blob(text[: found.start()] + text[found.end() :]), mode)

    return change


RUNTIME_IF = "    if: needs.changes.outputs.runtime == 'true'\n"
STEP = "      - name: Runtime tests (K-01, K-02, K-03, K-04)\n"
PLANTS: dict[str, tuple[Callable[[Throwaway], None], str]] = {
    "release-mode-value-300": (_bound("runtime-checked", "300"), "is 300, not 360"),
    "continue-on-error-beside-the-bound": (
        job_edit(
            CI, "runtime-checked", f"{BOUND_LINE}\n", f"{BOUND_LINE}\n    continue-on-error: true\n"
        ),
        "runtime-checked: continue-on-error",
    ),
    "release-mode-if-always-false": (
        job_edit(CI, "runtime-checked", RUNTIME_IF, "    if: false\n"),
        "job runtime-checked: if changed",
    ),
    "release-yml-runtime-timeout": (
        job_edit(RELEASE, "runtime", "    timeout-minutes: 60\n", "    timeout-minutes: 360\n"),
        f"{RELEASE} changes",
    ),
    "a-backup-file-touched": (modify("backup/README.md"), "backup/README.md changes"),
    "composition-timeout-removed": (_bound_dropped("runtime"), f"runtime: no explicit {TIMEOUT}"),
    "value-361": (_bound("runtime", "361"), "is 361, not 360"),
    "value-quoted": (_bound("runtime", '"360"'), "is '360', not 360"),
    "value-boolean": (_bound("runtime", "true"), "is True, not 360"),
    "value-zero": (_bound("runtime", "0"), "is 0, not 360"),
    "value-negative": (_bound("runtime", "-1"), "is -1, not 360"),
    "value-float": (_bound("runtime", "360.0"), "is 360.0, not 360"),
    "360-on-one-job-only": (_bound("runtime-checked", "75"), "is 75, not 360"),
    "a-second-comment-line-above-the-bound": (
        job_edit(CI, "runtime", f"{BOUND_LINE}\n", f"    # planted\n{BOUND_LINE}\n"),
        "differs beyond the bound",
    ),
    "a-step-level-timeout": (
        job_edit(CI, "runtime", STEP, f"{STEP}        timeout-minutes: 300\n"),
        "has its own timeout-minutes",
    ),
    "or-true-on-the-run-line": (
        job_edit(CI, "runtime", RUN_LINE, f"{RUN_LINE} || true"),
        "masks a failure",
    ),
    "release-mode-permissions": (
        job_edit(CI, "runtime-checked", "      packages: read\n", "      packages: write\n"),
        "job runtime-checked: permissions changed",
    ),
    "composition-needs": (
        job_edit(CI, "runtime", "    needs: changes\n", "    needs: [changes, images]\n"),
        "job runtime: needs changed",
    ),
    "another-job-retuned": (
        job_edit(CI, "backend", "    timeout-minutes: 15\n", "    timeout-minutes: 16\n"),
        "job backend changed",
    ),
    "a-workflow-level-key": (
        edit(CI, "  cancel-in-progress: ", "  cancel-in-progress: false && "),
        "workflow key 'concurrency' changed",
    ),
    "whitespace-only-elsewhere": (
        edit(CI, "  changes:\n    name: changes\n", "  changes:\n    name:  changes\n"),
        "differs beyond the bound",
    ),
    "keys-reordered-in-a-runtime-job": (
        job_edit(
            CI,
            "runtime",
            f"    needs: changes\n{RUNTIME_IF}",
            f"{RUNTIME_IF}    needs: changes\n",
        ),
        "differs beyond the bound",
    ),
}


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    """Selected for every git call of the check; its origin/main is the pinned head."""
    return Throwaway(tmp_path / "repo", HEAD, monkeypatch)


@pytest.mark.parametrize("case", sorted(PLANTS))
def test_eko125_k05_each_plant_alone_fails_on_both_bases(case: str, throwaway: Throwaway) -> None:
    change, fragment = PLANTS[case]
    planted = throwaway.commit(HEAD, change)
    for base in BASES:
        found = k05_violations(base, planted)
        assert any(fragment in problem for problem in found), (case, base, found)


def test_eko125_k05_the_verdict_ignores_the_live_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository whose HEAD, origin/main and $CHANGESET_BASE are all something else."""
    repo = Throwaway(tmp_path / "repo", EKO_1_20_BASE, monkeypatch)
    repo.checkout_files(EKO_1_20_BASE, CI)
    monkeypatch.setenv("CHANGESET_BASE", ABSENT)
    assert k05_violations(BASE, HEAD) == []
    planted = repo.commit(HEAD, PLANTS["release-mode-value-300"][0])
    assert "job runtime-checked: timeout-minutes is 300, not 360" in k05_violations(BASE, planted)
