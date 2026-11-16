"""EKO-1-15 K-02 (ADR-0004-C31) and K-03 over the release workflow itself.

K-02: each project image is built once, in one job; the image checks and the runtime tests run
on that build; the publish job pushes the loaded checked images, verifies their identity, and
renders the composition from the digests of those pushes; the runtime tests' `postgres` is the
pulled image whose digest the composition names.
EKO-1-26 K-03: the custom Keycloak image is a pushed project image — its digest is the run's own
push record, never a runtime pull; no step demands a registry digest the pipeline does not
publish, and every recorded ID reaches every identity and push step (K-04 lockstep).
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


def test_eko126_k03_project_digests_are_the_pushes_own_never_a_pull() -> None:
    """EKO-1-26 K-03: the five project images — the custom keycloak among them — take their
    digests from the publish job's own push record; none is re-pointed at a runtime pull."""
    assert rw.pushed_project_digest_violations(release()) == []


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


def _add_runtime_output(name: str, value: Any) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        outputs = changed["jobs"]["runtime"].setdefault("outputs", {})
        outputs[name] = value
        return changed

    return apply


def _set_env(name: str, needle: str, key: str, value: Any) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        steps = [s for s in changed["jobs"][name]["steps"] if needle in str(s.get("run", ""))]
        assert steps, (name, needle)
        env = steps[0].setdefault("env", {})
        if value is None:
            assert key in env, (name, key)
            del env[key]
        else:
            env[key] = value
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
    # EKO-1-26 K-03: the keycloak digest is the run's own push, never a pull re-pointed in.
    "k03-keycloak-digest-pulled": (
        rw.pushed_project_digest_violations,
        _add_runtime_output("keycloak", "${{ steps.pulled-digests.outputs.keycloak }}"),
    ),
    "k03-keycloak-render-flag": (
        rw.pushed_project_digest_violations,
        _rewrite_run("publish", "--out", '--keycloak "$KEYCLOAK_DIGEST" --out'),
    ),
    "k03-keycloak-render-env": (
        rw.pushed_project_digest_violations,
        _set_env(
            "publish",
            "release_composition render",
            "KEYCLOAK_DIGEST",
            "${{ needs.runtime.outputs.keycloak }}",
        ),
    ),
    # EKO-1-26 K-04: a release identity or push step that forgot the keycloak ID cannot verify
    # the family it built — every recorded ID must reach every step that checks identity.
    "k04-identity-missing-keycloak-id": (
        rw.build_once_violations,
        _set_env("runtime", "check-identity", "KEYCLOAK_ID", None),
    ),
    "k04-push-missing-keycloak-id": (
        rw.build_once_violations,
        _set_env("publish", "release-images.sh push", "KEYCLOAK_ID", None),
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
