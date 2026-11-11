"""EKO-1-15 K-07, static half: every pre-EKO-1-15 `ci.yml` job and step checks what it checks
today, with no permission added except `packages: read`; the development profile builds its
project images locally and names no image of the project registry.

The closed list of allowed differences also holds, since EKO-1-12 fix round 3 (2026-11-11) and on
the EKO-1-15 F-1 precedent, exactly one step: the keycloak pre-build of the release-mode job,
listed as `release_workflow.CI_KEYCLOAK_PREBUILD_STEP` and dropped once from each side.

Base: $CHANGESET_BASE, else origin/main (tests/static/test_k07_changeset.py). The runtime half
(the development profile started with the project registry unreachable) is not here.
"""

import copy
from typing import Any

import pytest
import yaml

from tests.static.test_k07_changeset import at_base, in_worktree
from tests.support import release_workflow as rw
from tests.support import workflow_checks as wc

CI = ".github/workflows/ci.yml"
Workflow = dict[Any, Any]
PROJECT_REGISTRY = "ghcr.io/tanercrb"
PROJECT_SERVICES = ("proxy", "frontend", "backend", "backup")


def base_and_head() -> tuple[Workflow, Workflow]:
    base, head = at_base(CI), in_worktree(CI)
    assert base is not None and head is not None
    return yaml.safe_load(base), yaml.safe_load(head)


def test_eko115_k07_ci_jobs_and_steps_unchanged() -> None:
    base, head = base_and_head()
    assert rw.ci_unchanged_violations(base, head) == []


def _job(name: str, key: str, value: Any) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name][key] = value
        return changed

    return apply


def _drop_step(name: str) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name]["steps"].pop()
        return changed

    return apply


def _step_if(name: str) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name]["steps"][-1]["if"] = "false"
        return changed

    return apply


def _insert_step(name: str, index: int, step: dict[str, Any]) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name]["steps"].insert(index, copy.deepcopy(step))
        return changed

    return apply


def _checkout_with(name: str, extra: dict[str, Any]) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        step = changed["jobs"][name]["steps"][0]
        step["with"] = {**(step.get("with") or {}), **extra}
        return changed

    return apply


def _step_env(name: str, index: int, env: dict[str, str]) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        step = changed["jobs"][name]["steps"][index]
        step["env"] = {**(step.get("env") or {}), **env}
        return changed

    return apply


def _rewrite_run(name: str, old: str, new: str) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        steps = [s for s in changed["jobs"][name]["steps"] if old in str(s.get("run", ""))]
        assert len(steps) == 1, (name, old)
        steps[0]["run"] = steps[0]["run"].replace(old, new)
        return changed

    return apply


def _drop_record_token(name: str) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        for step in changed["jobs"][name]["steps"]:
            (step.get("env") or {}).pop(wc.RECORD_TOKEN, None)
        return changed

    return apply


FAILING = {
    "step-dropped": _drop_step("backend"),
    "step-if-false": _step_if("frontend"),
    "job-if-added": _job("layers", "if", "false"),
    "contents-write": _job("backend", "permissions", {"contents": "write"}),
    "packages-write": _job("backend", "permissions", {"contents": "read", "packages": "write"}),
    "job-removed": lambda f: {**f, "jobs": {k: v for k, v in f["jobs"].items() if k != "runtime"}},
    "packages-read-on-a-job-reading-no-record": _job(
        "frontend", "permissions", {"contents": "read", "packages": "read"}
    ),
    "login-on-a-job-reading-no-record": _insert_step("frontend", 1, rw.CI_LOGIN_STEP),
    "login-with-a-stored-secret": _insert_step(
        "runtime",
        1,
        {**rw.CI_LOGIN_STEP, "env": {"TOKEN": "${{ secrets.GHCR_PAT }}", "ACTOR": "x"}},
    ),
    "fetch-depth-on-another-checkout": _checkout_with("images", {"fetch-depth": 0}),
    "record-token-on-a-job-reading-no-record": _step_env(
        "frontend", -1, {"RELEASE_RECORD_TOKEN": "${{ github.token }}"}
    ),
    "runtime-marker-other-than-allowed": _rewrite_run(
        "runtime", '"runtime or previous_release"', '"runtime or slow"'
    ),
    "compat-step-other-than-allowed": _rewrite_run(
        "backend", "tests.support.openapi_compat", "tests.support.openapi_compat --previous x.json"
    ),
}


@pytest.mark.parametrize("case_id", sorted(FAILING))
def test_eko115_k07_ci_check_fails_on_a_plant(case_id: str) -> None:
    base, head = base_and_head()
    assert rw.ci_unchanged_violations(base, FAILING[case_id](head)) != [], case_id


def test_eko115_k07_contrast_packages_read_is_allowed_on_a_record_reading_job() -> None:
    base, head = base_and_head()
    planted = _job("backend", "permissions", {"contents": "read", "packages": "read"})(head)
    assert rw.ci_unchanged_violations(base, planted) == []


def test_eko115_k07_ci_reads_the_record_in_the_runtime_job() -> None:
    _, head = base_and_head()
    runtime = head["jobs"]["runtime"]
    assert runtime["permissions"] == {"contents": "read", "packages": "read"}
    assert rw.CI_LOGIN_STEP in runtime["steps"]
    assert runtime["steps"][0]["with"]["fetch-depth"] == 0
    tests = [s for s in runtime["steps"] if "pytest" in str(s.get("run", ""))]
    assert tests[0]["run"] == rw.CI_RUNTIME_RUN
    assert tests[0]["env"]["RELEASE_RECORD_TOKEN"] == "${{ github.token }}"


def test_eko115_k07_ci_reads_the_record_in_the_backend_job() -> None:
    _, head = base_and_head()
    backend = head["jobs"]["backend"]
    assert backend["permissions"] == {"contents": "read", "packages": "read"}
    assert rw.CI_LOGIN_STEP in backend["steps"]
    assert backend["steps"][0]["with"]["fetch-depth"] == 0
    compat = [s for s in backend["steps"] if "openapi_compat" in str(s.get("run", ""))]
    assert len(compat) == 1
    assert compat[0]["run"] == rw.CI_COMPAT_RUN
    assert compat[0]["env"]["RELEASE_RECORD_TOKEN"] == "${{ github.token }}"


# C-3: the narrowed read-only rule of EKO-1-06 K-05 (exception EKO-1-15/weakening-1) ------------


def test_eko115_c3_packages_read_only_on_a_record_reading_job() -> None:
    _, head = base_and_head()
    assert wc.read_only_token(head) == []
    reading = _step_env("backend", -1, {"RELEASE_RECORD_TOKEN": "${{ github.token }}"})(head)
    granted = _job("backend", "permissions", {"contents": "read", "packages": "read"})(reading)
    assert wc.read_only_token(granted) == []


@pytest.mark.parametrize(
    "change",
    [
        _job("frontend", "permissions", {"contents": "read", "packages": "read"}),
        _job("runtime", "permissions", {"contents": "write", "packages": "read"}),
        _job("runtime", "permissions", {"contents": "read", "packages": "write"}),
        _job("runtime", "permissions", {"contents": "read", "packages": "read", "issues": "read"}),
        lambda f: {**f, "permissions": {"contents": "read", "packages": "read"}},
        lambda f: _job("frontend", "permissions", {"contents": "read", "packages": "read"})(
            _step_env("frontend", -1, {"RELEASE_RECORD_TOKEN": "${{ github.token }}"})(f)
        ),
        _drop_record_token("runtime"),
    ],
    ids=[
        "no-record",
        "contents-write",
        "packages-write",
        "extra-scope",
        "workflow-level",
        "record-token-on-an-unlisted-job",
        "listed-job-reading-no-record",
    ],
)
def test_eko115_c3_read_only_rule_fails_on_any_other_permission(change: Any) -> None:
    _, head = base_and_head()
    assert wc.read_only_token(change(head)) != []


def test_eko115_k07_development_profile_builds_locally(rendered_dev: dict[str, Any]) -> None:
    services = rendered_dev["services"]
    assert [n for n in PROJECT_SERVICES if "build" not in services[n]] == []
    named = [n for n, s in services.items() if PROJECT_REGISTRY in str(s.get("image", ""))]
    assert named == []
