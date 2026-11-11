"""EKO-1-19 K-03, K-04, K-06: release mode in `ci.yml`, checked against `release.yml`.

Each check returns its violations, empty when the rule holds. The release-mode jobs copy the
release workflow's image build and load step for step; this module compares the two texts, so
a drift in either shows up here rather than on the next release tag.
"""

import re
from typing import Any

from tests.support import release_workflow as rw
from tests.support import workflow_checks as wc

Workflow = dict[Any, Any]
BUILD_JOB = "checked-images"
RELEASE_MODE_JOB = "runtime-checked"
BUILD_MODE_JOB = "runtime"
ARTIFACT = "checked-images"
CHECKED_PAIRS = tuple(f"{name}={rw.checked(name)}" for name in rw.PROJECT_IMAGES)
ID_OUTPUTS = {f"{name}-id": f"${{{{ steps.ids.outputs.{name} }}}}" for name in rw.PROJECT_IMAGES}
ID_ENV = {
    f"{name.upper()}_ID": f"${{{{ needs.{BUILD_JOB}.outputs.{name}-id }}}}"
    for name in rw.PROJECT_IMAGES
}
RELEASE_MODE_PERMISSIONS = {"contents": "read", "packages": "read"}
# A download with any of these inputs can read another run's artifact.
FOREIGN_ARTIFACT_INPUTS = ("run-id", "github-token", "repository")
SNAPSHOT = "uv run python -m tests.support.session_images snapshot"
SESSION_CHECK = "uv run python -m tests.support.session_images check"
# EKO-1-12 K-04 (fix round 3, 2026-11-11): keycloak has no checked counterpart (release-images.sh
# NAMES is the four project images; the digest join is deferred to #118), so its composition image
# must already exist when the snapshot is taken, never be built by the session's first compose up.
# The project name below is the listed step's own (release_workflow.CI_KEYCLOAK_PREBUILD_STEP).
KEYCLOAK_PREBUILD = "eko-ci-keycloak-prebuild"
# K-06: what would write to the registry or the repository from a pull request's run.
PUSHES = re.compile(
    r"\bdocker\s+(?:image\s+)?push\b|\bdocker\s+(?:image\s+)?tag\b[^\n]*ghcr\.io"
    r"|\boras\s+push\b|\bgit\s+push\b|build-push-action"
)


def _jobs(flow: Workflow) -> dict[str, Any]:
    jobs: dict[str, Any] = flow.get("jobs") or {}
    return jobs


def _step(flow: Workflow, job: str, needle: str) -> tuple[int, dict[str, Any]]:
    for index, step in enumerate(rw._steps_of(flow, job)):
        if needle in str(step.get("run", "")) or needle in str(step.get("uses", "")):
            return index, step
    return -1, {}


def _pytest_step(flow: Workflow, job: str) -> dict[str, Any]:
    return _step(flow, job, "pytest")[1]


def condition_violations(ci: Workflow) -> list[str]:
    """Both release-mode jobs run exactly when the build-mode runtime job runs."""
    jobs = _jobs(ci)
    problems = []
    if BUILD_MODE_JOB not in jobs:
        return [f"no {BUILD_MODE_JOB} job"]
    wanted = jobs[BUILD_MODE_JOB].get("if")
    for name in (BUILD_JOB, RELEASE_MODE_JOB):
        job = jobs.get(name)
        if job is None:
            problems.append(f"no {name} job")
            continue
        if job.get("if") != wanted or wanted != wc.TRIGGER_CONDITION:
            problems.append(f"{name}: condition {job.get('if')!r}, not {wanted!r}")
        if "changes" not in rw._needs(job):
            problems.append(f"{name}: does not need the changes job")
    if RELEASE_MODE_JOB in jobs and BUILD_JOB not in rw._needs(jobs[RELEASE_MODE_JOB]):
        problems.append(f"{RELEASE_MODE_JOB}: does not need {BUILD_JOB}")
    return problems


def build_job_violations(ci: Workflow, release: Workflow) -> list[str]:
    """The release workflow's five builds, ID record and save, on Docker alone (ADR-0001-C4;
    EKO-1-26: the custom Keycloak image is the fifth project image)."""
    job = _jobs(ci).get(BUILD_JOB)
    if job is None:
        return [f"no {BUILD_JOB} job"]
    problems = []
    for step in job.get("steps") or []:
        if wc.RUNTIME_SETUP_ACTIONS.search(str(step.get("uses", ""))):
            problems.append(f"{BUILD_JOB}: {step['uses']}")
        if wc.RUNTIME_INSTALL.search(str(step.get("run", ""))):
            problems.append(f"{BUILD_JOB}: step {step.get('name')!r} runs a Python or Node.js tool")
    for needle in ("docker build", "docker image inspect --format '{{.Id}}'", "docker save"):
        ours, theirs = _step(ci, BUILD_JOB, needle)[1], _step(release, rw.IMAGES_JOB, needle)[1]
        if not theirs or ours.get("run") != theirs.get("run"):
            problems.append(f"{BUILD_JOB}: the {needle!r} step is not release.yml's")
    if _step(ci, BUILD_JOB, "docker image inspect")[1].get("id") != "ids":
        problems.append(f"{BUILD_JOB}: the image IDs are not recorded by a step with id 'ids'")
    if job.get("outputs") != ID_OUTPUTS:
        problems.append(f"{BUILD_JOB}: outputs {job.get('outputs')!r}, not the five image IDs")
    ours = _step(ci, BUILD_JOB, "actions/upload-artifact@")[1]
    theirs = _step(release, rw.IMAGES_JOB, "actions/upload-artifact@")[1]
    if not theirs or ours != theirs:
        problems.append(f"{BUILD_JOB}: the upload is not release.yml's")
    return problems


def release_mode_job_violations(ci: Workflow, release: Workflow) -> list[str]:
    """Load the same run's archive, check identity, run the build-mode pytest call on the checked
    images, then check identity again and that the session built no image (K-04)."""
    job = _jobs(ci).get(RELEASE_MODE_JOB)
    if job is None:
        return [f"no {RELEASE_MODE_JOB} job"]
    problems = []
    if job.get("permissions") != RELEASE_MODE_PERMISSIONS:
        problems.append(f"{RELEASE_MODE_JOB}: permissions {job.get('permissions')!r}")
    download_at, download = _step(ci, RELEASE_MODE_JOB, "actions/download-artifact@")
    theirs = _step(release, rw.RUNTIME_JOB, "actions/download-artifact@")[1]
    if not theirs or download != theirs:
        problems.append(f"{RELEASE_MODE_JOB}: the download is not release.yml's")
    foreign = set(FOREIGN_ARTIFACT_INPUTS) & set(download.get("with") or {})
    if foreign:
        problems.append(f"{RELEASE_MODE_JOB}: the download reads another run ({sorted(foreign)})")
    identity_steps = [
        (index, step)
        for index, step in enumerate(rw._steps_of(ci, RELEASE_MODE_JOB))
        if rw.IDENTITY in str(step.get("run", ""))
    ]
    load_at, load = _step(ci, RELEASE_MODE_JOB, "docker load")
    their_load = _step(release, rw.RUNTIME_JOB, "docker load")[1]
    if not their_load or load.get("run") != their_load.get("run"):
        problems.append(f"{RELEASE_MODE_JOB}: the load is not release.yml's load and check")
    pytest_at, tests = _step(ci, RELEASE_MODE_JOB, "pytest")
    problems += _pytest_violations(ci, release, tests)
    for index, step in identity_steps:
        if (step.get("env") or {}) != ID_ENV:
            problems.append(f"{RELEASE_MODE_JOB}: identity step {index} is not given the build IDs")
    before = [i for i, _ in identity_steps if i < pytest_at]
    after = [i for i, _ in identity_steps if i > pytest_at]
    if pytest_at < 0 or not before or not after:
        problems.append(f"{RELEASE_MODE_JOB}: identity is not checked before and after the tests")
    if not 0 <= download_at < load_at < pytest_at:
        problems.append(f"{RELEASE_MODE_JOB}: the tests do not run on the loaded archive")
    snapshot_at = _step(ci, RELEASE_MODE_JOB, SNAPSHOT)[0]
    check_at = _step(ci, RELEASE_MODE_JOB, SESSION_CHECK)[0]
    if not 0 <= snapshot_at < pytest_at < check_at:
        problems.append(f"{RELEASE_MODE_JOB}: no image snapshot before and image check after")
    prebuild_at = _step(ci, RELEASE_MODE_JOB, KEYCLOAK_PREBUILD)[0]
    if not 0 <= prebuild_at < snapshot_at:
        problems.append(f"{RELEASE_MODE_JOB}: the keycloak image is not built before the snapshot")
    return problems


def _pytest_violations(ci: Workflow, release: Workflow, tests: dict[str, Any]) -> list[str]:
    problems = []
    build_mode = _pytest_step(ci, BUILD_MODE_JOB)
    released = _pytest_step(release, rw.RUNTIME_JOB)
    if not tests or tests.get("run") != build_mode.get("run") or tests["run"] != released["run"]:
        problems.append(f"{RELEASE_MODE_JOB}: pytest is not the build-mode and release call")
    if tests.get("working-directory") != build_mode.get("working-directory"):
        problems.append(f"{RELEASE_MODE_JOB}: pytest runs in another directory")
    env = tests.get("env") or {}
    given = str(env.get("EKO_CHECKED_IMAGES", "")).split()
    if sorted(given) != sorted(CHECKED_PAIRS) or len(given) != len(set(given)):
        problems.append(f"{RELEASE_MODE_JOB}: EKO_CHECKED_IMAGES is {given!r}")
    if env.get("EKO_CHECKED_IMAGES") != (released.get("env") or {}).get("EKO_CHECKED_IMAGES"):
        problems.append(f"{RELEASE_MODE_JOB}: EKO_CHECKED_IMAGES differs from release.yml's")
    if env.get(wc.RECORD_TOKEN) != "${{ github.token }}":
        problems.append(f"{RELEASE_MODE_JOB}: the tests are not given the record token")
    # K-01: the mode is the only difference between the two jobs' test sessions.
    rest = {k: v for k, v in env.items() if k != "EKO_CHECKED_IMAGES"}
    if rest != (build_mode.get("env") or {}):
        problems.append(f"{RELEASE_MODE_JOB}: the tests' env differs from build mode's by more")
    return problems


def push_violations(flow: Workflow) -> list[str]:
    """K-06: no step pushes an image, tags one for the registry or pushes to Git."""
    return [
        f"{job}: step {step.get('name')!r} pushes ({match.group(0)!r})"
        for job, step in wc._steps(flow)
        for match in PUSHES.finditer(f"{step.get('run', '')} {step.get('uses', '')}")
    ]


def release_mode_violations(ci: Workflow, release: Workflow) -> list[str]:
    return (
        condition_violations(ci)
        + build_job_violations(ci, release)
        + release_mode_job_violations(ci, release)
        + push_violations(ci)
    )
