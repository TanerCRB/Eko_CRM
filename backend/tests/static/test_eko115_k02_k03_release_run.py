"""EKO-1-15 K-02 (ADR-0004-C31) and K-03 over the release workflow itself.

K-02: each project image is built once, in one job; the image checks and the runtime tests run
on that build; the publish job pushes the loaded checked images, verifies their identity, and
renders the composition from the digests of those pushes; the runtime tests' `postgres` and
`keycloak` are the ones whose digests the composition names.
K-03: publishing depends, transitively, on each of the four checks, and none of them can end as
success without running.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.support import release_workflow as rw
from tests.support.repo import REPO_ROOT

RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"
Workflow = dict[Any, Any]


def release() -> Workflow:
    loaded: Workflow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    return loaded


def test_eko115_k02_each_image_built_once_and_published_as_checked() -> None:
    assert rw.build_once_violations(release()) == []


def test_eko115_k02_third_party_digests_come_from_the_runtime_tests() -> None:
    assert rw.third_party_digest_violations(release()) == []


def test_eko115_k03_publishing_needs_every_check() -> None:
    assert rw.publish_dependency_violations(release()) == []


def test_eko115_k03_no_check_can_pass_without_running() -> None:
    assert rw.check_masking_violations(release()) == []


def _job(name: str, key: str, value: Any) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name][key] = value
        return changed

    return apply


def _without_need(name: str, need: str) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name]["needs"] = [n for n in changed["jobs"][name]["needs"] if n != need]
        return changed

    return apply


def _append_step(name: str, step: dict[str, Any]) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][name]["steps"].insert(-1, step)
        return changed

    return apply


def _step_where(name: str, needle: str, key: str, value: Any) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        steps = [s for s in changed["jobs"][name]["steps"] if needle in str(s.get("run", ""))]
        assert steps, (name, needle)
        steps[0][key] = value
        return changed

    return apply


def _rewrite_run(name: str, old: str, new: str) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        hits = 0
        for step in changed["jobs"][name]["steps"]:
            if old in str(step.get("run", "")):
                step["run"] = step["run"].replace(old, new)
                hits += 1
        assert hits, (name, old)
        return changed

    return apply


Check = Callable[[Workflow], list[str]]
PLANTS: dict[str, tuple[Check, Callable[[Workflow], Workflow]]] = {
    "k02-publish-rebuilds": (
        rw.build_once_violations,
        _append_step("publish", {"name": "rebuild", "run": "docker build -t x backend"}),
    ),
    "k02-runtime-rebuilds-unchecked": (
        rw.build_once_violations,
        _step_where("runtime", "pytest", "env", {}),
    ),
    "k02-a-second-build-job": (
        rw.build_once_violations,
        _append_step("runtime", {"name": "b", "run": "docker compose build"}),
    ),
    "k02-publish-skips-identity-check": (
        rw.build_once_violations,
        _rewrite_run("publish", "check-identity", "true-identity"),
    ),
    "k02-third-party-by-tag": (
        rw.third_party_digest_violations,
        _rewrite_run("runtime", "pulled-digests", "pinned-digests"),
    ),
    "k03-runtime-not-needed": (
        rw.publish_dependency_violations,
        _without_need("publish", "runtime"),
    ),
    "k03-frontend-not-needed": (
        rw.publish_dependency_violations,
        _without_need("publish", "frontend"),
    ),
    "k03-images-continue-on-error": (
        rw.check_masking_violations,
        _job("images", "continue-on-error", True),
    ),
    "k03-image-check-step-continue-on-error": (
        rw.check_masking_violations,
        _step_where("images", "image-check.sh", "continue-on-error", True),
    ),
    "k03-publish-always": (rw.check_masking_violations, _job("publish", "if", "always()")),
    "k03-runtime-skipped": (rw.check_masking_violations, _job("runtime", "if", "false")),
    "k03-masked-pytest": (rw.check_masking_violations, _rewrite_run("backend", "-v", "-v || true")),
}


@pytest.mark.parametrize("case_id", sorted(PLANTS))
def test_eko115_k02_k03_check_fails_on_a_plant(case_id: str) -> None:
    check, change = PLANTS[case_id]
    flow = release()
    assert check(flow) == [], f"{case_id}: the release workflow must pass first"
    assert check(change(flow)) != [], case_id
