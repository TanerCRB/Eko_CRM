"""EKO-1-19 K-03, K-04 (wiring), K-06: `ci.yml` runs the runtime suite on images built once in the
same run and loaded under the EKO_CHECKED_IMAGES names, exactly where the build-mode runtime job
runs, and nothing in it writes to the registry. Each check fails on a one-change plant.

The unchanged-job and unchanged-release checks are EKO-1-19's claims and are judged on PR #96's
parents (EKO_1_19_BASE, EKO_1_19_HEAD), read through Git objects only (EKO-1-23, #110): never
`$CHANGESET_BASE`, `origin/main` or the working tree. "Builds once" stays judged on the live file:
EKO-1-26 widened that live invariant to the five project images, and its carrier is the dedicated
test below, so EKO-1-19's pair claims stay insensitive to the working tree (EKO-1-23's harness
K-05 block judges that carrier with a swapped live tree).
"""

import copy
import re
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.support import release_mode_ci as rm
from tests.support import release_workflow as rw
from tests.support import workflow_checks as wc
from tests.support.fixed_pair import file_at
from tests.support.repo import REPO_ROOT

CI = ".github/workflows/ci.yml"
RELEASE = ".github/workflows/release.yml"
# PR #96 (EKO-1-19): 794c04a's parents; its merge base is the first parent.
EKO_1_19_BASE = "e895ce17ad46b8f50df6b92b2dc11ed9af8af110"
EKO_1_19_HEAD = "726befdd86cebbd67d1796f5cc79f4f7121685d3"
Workflow = dict[Any, Any]


def load(path: str) -> Workflow:
    loaded: Workflow = yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))
    return loaded


def ci() -> Workflow:
    return load(CI)


def release() -> Workflow:
    return load(RELEASE)


def test_eko119_k03_ci_runs_release_mode_like_the_release_run() -> None:
    assert rm.release_mode_violations(ci(), release()) == []


def test_eko119_k06_ci_pushes_nothing() -> None:
    assert rm.push_violations(ci()) == []


def test_eko119_k06_no_new_job_holds_packages_write() -> None:
    flows = {"ci.yml": ci(), "release.yml": release()}
    assert rw.registry_write_violations(flows) == []
    assert rw.registry_login_violations(flows) == []


def test_eko119_g6_record_jobs_widened_by_exactly_the_release_mode_job() -> None:
    assert wc.RECORD_JOBS == ("backend", "runtime", rm.RELEASE_MODE_JOB)
    assert wc.read_only_token(ci()) == []


def test_eko119_k03_release_mode_jobs_install_no_runtime_in_the_build() -> None:
    assert rm.build_job_violations(ci(), release()) == []


# Unchanged: every job ci.yml had, and release.yml ---------------------------------------------


def job_blocks(text: str) -> dict[str, str]:
    """Each job's own lines in the file, without the comment lines that open the next job."""
    lines = text.split("\n")
    start = lines.index("jobs:") + 1
    blocks: dict[str, list[str]] = {}
    current = ""
    for line in lines[start:]:
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
        if match:
            current = match.group(1)
            blocks[current] = []
        if current:
            blocks[current].append(line)
    trimmed = {}
    for name, block in blocks.items():
        while block and (not block[-1].strip() or block[-1].lstrip().startswith("#")):
            block.pop()
        trimmed[name] = "\n".join(block)
    return trimmed


def assert_existing_jobs_unchanged(base: str, head: str) -> None:
    """Byte-identical but for a retuned `timeout-minutes` (wc.timeout_lines_masked, EKO-1-20)."""
    before = {n: wc.timeout_lines_masked(b) for n, b in job_blocks(base).items()}
    after = {n: wc.timeout_lines_masked(b) for n, b in job_blocks(head).items()}
    assert {name: after.get(name) for name in before} == before
    base_flow, head_flow = yaml.safe_load(base), yaml.safe_load(head)
    base_jobs = {name: wc.timeout_masked(job) for name, job in base_flow["jobs"].items()}
    assert {name: wc.timeout_masked(head_flow["jobs"].get(name)) for name in base_jobs} == base_jobs
    head_keys = {k: v for k, v in head_flow.items() if k != "jobs"}
    assert head_keys == {k: v for k, v in base_flow.items() if k != "jobs"}


def eko_1_19_pair(
    path: str, base: str = EKO_1_19_BASE, head: str = EKO_1_19_HEAD
) -> tuple[str | None, str | None]:
    """`path` as EKO-1-19's base and head hold it; a missing commit raises."""
    return file_at(base, path), file_at(head, path)


def test_eko119_k03_every_existing_ci_job_is_byte_identical() -> None:
    base, head = eko_1_19_pair(CI)
    assert base is not None and head is not None
    assert_existing_jobs_unchanged(base, head)


def test_eko119_k06_release_workflow_unchanged() -> None:
    base, head = eko_1_19_pair(RELEASE)
    assert base is not None and base == head


def test_eko126_k04_live_release_builds_the_five_project_images_once() -> None:
    """EKO-1-19's "builds once", judged on the live `release.yml` — what every head must meet
    (ADR-0004-C31). EKO-1-26 K-04 widened the family to the custom Keycloak image; the live half
    moves out of the pair-identical check here so the pair stays the pair and this stays live.
    EKO-1-23's harness K-05 block reads exactly this carrier with a swapped live tree."""
    assert rw.build_once_violations(release()) == []


# Plants: one change each ---------------------------------------------------------------------


def _change(apply: Callable[[Workflow], None]) -> Callable[[Workflow], Workflow]:
    def changed(flow: Workflow) -> Workflow:
        copied = copy.deepcopy(flow)
        apply(copied)
        return copied

    return changed


def _tests_step(flow: Workflow) -> dict[str, Any]:
    return rm._pytest_step(flow, rm.RELEASE_MODE_JOB)


def _job(flow: Workflow, name: str = rm.RELEASE_MODE_JOB) -> dict[str, Any]:
    job: dict[str, Any] = flow["jobs"][name]
    return job


def _drop_step(job: str, needle: str) -> Callable[[Workflow], None]:
    def apply(flow: Workflow) -> None:
        steps = _job(flow, job)["steps"]
        index = rm._step(flow, job, needle)[0]
        steps.pop(index)

    return apply


def _last_identity_dropped(flow: Workflow) -> None:
    steps = _job(flow)["steps"]
    index = max(i for i, s in enumerate(steps) if rw.IDENTITY in str(s.get("run", "")))
    steps.pop(index)


def _download_with(key: str) -> Callable[[Workflow], None]:
    def apply(flow: Workflow) -> None:
        rm._step(flow, rm.RELEASE_MODE_JOB, "actions/download-artifact@")[1]["with"][key] = "1"

    return apply


def _env(key: str, value: Any) -> Callable[[Workflow], None]:
    def apply(flow: Workflow) -> None:
        env = _tests_step(flow)["env"]
        if value is None:
            del env[key]
        else:
            env[key] = value

    return apply


def _set_job(key: str, value: Any, name: str = rm.RELEASE_MODE_JOB) -> Callable[[Workflow], None]:
    def apply(flow: Workflow) -> None:
        _job(flow, name)[key] = value

    return apply


def _append_run(run: str, name: str = rm.RELEASE_MODE_JOB) -> Callable[[Workflow], None]:
    def apply(flow: Workflow) -> None:
        _job(flow, name)["steps"].append({"name": "planted", "run": run})

    return apply


def _narrowed(flow: Workflow) -> None:
    step = _tests_step(flow)
    step["run"] = step["run"] + " -k backup"


def _build_flag(flow: Workflow) -> None:
    step = rm._step(flow, rm.BUILD_JOB, "docker build")[1]
    step["run"] = step["run"].replace("backup\n", "backup --no-cache\n")


def _save_without_keycloak(flow: Workflow) -> None:
    """EKO-1-26 K-04: the archive loses the custom Keycloak image — drift between the files."""
    step = rm._step(flow, rm.BUILD_JOB, "docker save")[1]
    step["run"] = step["run"].replace(" eko-crm/keycloak:checked", "")


def _keycloak_id_dropped(flow: Workflow) -> None:
    """EKO-1-26 K-04: an identity step that is not given the keycloak ID verifies four of five."""
    steps = [s for s in _job(flow)["steps"] if rw.IDENTITY in str(s.get("run", ""))]
    del steps[0]["env"]["KEYCLOAK_ID"]


def _keycloak_id_output_dropped(flow: Workflow) -> None:
    del _job(flow, rm.BUILD_JOB)["outputs"]["keycloak-id"]


def _setup_uv_in_build(flow: Workflow) -> None:
    _job(flow, rm.BUILD_JOB)["steps"].insert(1, {"uses": "astral-sh/setup-uv@" + "0" * 40})


def _rebuilds_in_release_mode(flow: Workflow) -> None:
    """EKO-1-26 K-01/K-02 (route A): a Compose build step re-enters the release-mode job. The
    transitional EKO-1-12 allowance (its pre-build step, tolerated only before the K-04 snapshot)
    is gone — the fifth image is placed checked and built outside the session — so a build in
    this job is red wherever it sits, not tolerated anywhere."""
    _append_run("docker compose --profile dev build keycloak")(flow)


PR_ONLY = f"github.event_name == 'pull_request' && {wc.TRIGGER_CONDITION}"
PLANTS: dict[str, Callable[[Workflow], None]] = {
    # K-03 (a), (b), (c)
    "checked-images-dropped": _env("EKO_CHECKED_IMAGES", None),
    "checked-images-empty": _env("EKO_CHECKED_IMAGES", ""),
    "checked-images-three": _env(
        "EKO_CHECKED_IMAGES", " ".join(p for p in rm.CHECKED_PAIRS if "backup" not in p)
    ),
    # EKO-1-26 K-04: the family list missing only keycloak (the fourth pair kept) is drift.
    "checked-images-no-keycloak": _env(
        "EKO_CHECKED_IMAGES", " ".join(p for p in rm.CHECKED_PAIRS if not p.startswith("keycloak"))
    ),
    "pytest-narrowed": _narrowed,
    "pull-request-only": _set_job("if", PR_ONLY),
    "build-job-pull-request-only": _set_job("if", PR_ONLY, rm.BUILD_JOB),
    "no-changes-need": _set_job("needs", [rm.BUILD_JOB]),
    "record-token-dropped": _env(wc.RECORD_TOKEN, None),
    "extra-test-env": _env("RELEASE_TAG", "v9.9.9"),
    # same-run archive, loaded and identified
    "download-run-id": _download_with("run-id"),
    "download-github-token": _download_with("github-token"),
    "no-load": _drop_step(rm.RELEASE_MODE_JOB, "docker load"),
    "build-flag-added": _build_flag,
    "no-save": _drop_step(rm.BUILD_JOB, "docker save"),
    "setup-uv-in-build": _setup_uv_in_build,
    # EKO-1-26 K-04: keycloak prepared in one place only must not drift from the release run.
    "save-drops-keycloak": _save_without_keycloak,
    "identity-drops-keycloak-id": _keycloak_id_dropped,
    "build-drops-keycloak-id-output": _keycloak_id_output_dropped,
    # K-04 (i), (ii) wiring
    "no-identity-after-tests": _last_identity_dropped,
    "no-snapshot": _drop_step(rm.RELEASE_MODE_JOB, rm.SNAPSHOT),
    "no-session-check": _drop_step(rm.RELEASE_MODE_JOB, rm.SESSION_CHECK),
    # K-04 (iii) (EKO-1-26): the release-mode job builds nothing — the superseded pre-build is red
    "release-mode-rebuilds-keycloak": _rebuilds_in_release_mode,
    # K-06 (b)
    "docker-push": _append_run("docker push eko-crm/backend:checked"),
    "tag-for-registry": _append_run("docker tag eko-crm/backend:checked ghcr.io/tanercrb/x:1"),
    "git-push": _append_run("git push origin HEAD", rm.BUILD_JOB),
}


@pytest.mark.parametrize("case_id", sorted(PLANTS))
def test_eko119_k03_check_fails_on_a_one_change_plant(case_id: str) -> None:
    flow = ci()
    assert rm.release_mode_violations(flow, release()) == [], "the repository's ci.yml first"
    assert rm.release_mode_violations(_change(PLANTS[case_id])(flow), release()) != [], case_id


def test_eko119_k06_packages_write_on_the_release_mode_job_is_refused() -> None:
    planted = _change(_set_job("permissions", {"contents": "read", "packages": "write"}))(ci())
    assert rw.registry_write_violations({"ci.yml": planted, "release.yml": release()}) != []


def test_eko119_g6_packages_read_on_a_job_outside_record_jobs_is_refused() -> None:
    planted = copy.deepcopy(ci())
    planted["jobs"]["runtime-checked-2"] = planted["jobs"][rm.RELEASE_MODE_JOB]
    assert wc.read_only_token(planted) != []
