"""K-05: the CI workflow's triggers, job conditions and hygiene; each check fails on a fixture."""

import copy
import re
import subprocess
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.support import workflow_checks as wc
from tests.support.repo import REPO_ROOT, bash

WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
REGISTER = REPO_ROOT / "docs" / "architecture" / "architecture-sensitive-paths.md"
TRIGGER = REPO_ROOT / "scripts" / "ci-runtime-trigger.sh"
Workflow = dict[Any, Any]


def workflow() -> Workflow:
    loaded: Workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return loaded


def all_workflows() -> dict[str, Workflow]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
    }


def runtime_job_runs_for(*paths: str) -> bool:
    result = subprocess.run(
        [bash(), str(TRIGGER), "--paths", "-"],
        input="\n".join(paths) + "\n",
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() == "true"


def register_globs() -> list[str]:
    rows = re.findall(r"^\| `([^`]+)` \|", REGISTER.read_text(encoding="utf-8"), re.MULTILINE)
    return [glob for glob in rows if "<" not in glob]


def sample_path(glob: str) -> str:
    """A path the glob matches: each wildcard replaced by a literal segment."""
    return glob.replace("**/", "x/").replace("**", "x").replace("*", "x")


# The path filter against the register ------------------------------------------------------


@pytest.mark.parametrize("glob", register_globs())
def test_k05_every_register_glob_runs_the_runtime_job(glob: str) -> None:
    assert runtime_job_runs_for(sample_path(glob)), glob


def test_k05_register_holds_the_new_gitignore_rows() -> None:
    assert {".gitignore", "**/.gitignore"} <= set(register_globs())


@pytest.mark.parametrize(
    "path",
    ["backend/tests/runtime/test_k01_startup.py", "backend/tests/support/compose_checks.py"],
)
def test_k05_a_runtime_test_file_alone_runs_the_runtime_job(path: str) -> None:
    assert runtime_job_runs_for(path)


@pytest.mark.parametrize("path", ["README.md", "docs/PLAN.md", "backend/tests/unit/test_x.py"])
def test_k05_a_non_sensitive_path_skips_the_runtime_job(path: str) -> None:
    assert not runtime_job_runs_for(path)


def test_k05_trigger_script_self_test_passes() -> None:
    result = subprocess.run([bash(), str(TRIGGER), "--self-test"], cwd=REPO_ROOT)
    assert result.returncode == 0


# Workflow checks on the repository ---------------------------------------------------------


def test_k05_ci_workflow_job_conditions() -> None:
    assert wc.job_conditions(workflow()) == []


def test_k05_adr0001_c4_image_job_installs_no_python_or_node() -> None:
    assert wc.image_job_installs_no_runtime(workflow()) == []


def test_k05_a_failing_test_fails_the_run() -> None:
    assert wc.failures_fail_the_run(workflow()) == []


def test_k05_ci_workflow_token_is_read_only() -> None:
    assert wc.read_only_token(workflow()) == []


@pytest.mark.parametrize("name", sorted(all_workflows()))
def test_k05_actions_pinned_and_no_persisted_credentials(name: str) -> None:
    flow = all_workflows()[name]
    assert wc.actions_pinned(flow) + wc.checkout_without_credentials(flow) == []


@pytest.mark.parametrize("name", sorted(all_workflows()))
def test_k07_no_secret_in_a_workflow_env_block(name: str, secret_inventory: set[str]) -> None:
    assert wc.no_secrets(all_workflows()[name], secret_inventory) == []


# Contrasts: one change each -----------------------------------------------------------------


def _set(path: list[Any], value: Any) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        node = changed
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        return changed

    return apply


def _step(job: str, index: int, key: str, value: Any) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][job]["steps"][index][key] = value
        return changed

    return apply


def _append_step(job: str, step: dict[str, Any]) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        changed["jobs"][job]["steps"].append(step)
        return changed

    return apply


def _last_run(job: str, suffix: str) -> Callable[[Workflow], Workflow]:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        step = changed["jobs"][job]["steps"][-1]
        step["run"] = step["run"] + suffix
        return changed

    return apply


CONTRASTS: dict[str, tuple[Callable[[Workflow], list[str]], Callable[[Workflow], Workflow]]] = {
    "continue-on-error-job": (
        wc.failures_fail_the_run,
        _set(["jobs", "backend", "continue-on-error"], True),
    ),
    "continue-on-error-step": (
        wc.failures_fail_the_run,
        _step("backend", -1, "continue-on-error", True),
    ),
    "or-true": (wc.failures_fail_the_run, _last_run("backend", " || true")),
    "frontend-or-true": (wc.failures_fail_the_run, _last_run("frontend", " || true")),
    "paths-filter": (wc.job_conditions, _set([True, "pull_request"], {"paths": ["backend/**"]})),
    "runtime-unconditioned": (wc.job_conditions, _set(["jobs", "runtime", "if"], "always()")),
    "images-unconditioned": (wc.job_conditions, _set(["jobs", "images", "if"], "true")),
    "backend-conditional": (wc.job_conditions, _set(["jobs", "backend", "if"], "false")),
    "push-not-main": (wc.job_conditions, _set([True, "push"], {"branches": ["develop"]})),
    "setup-python-in-images": (
        wc.image_job_installs_no_runtime,
        _append_step("images", {"uses": "actions/setup-python@" + "0" * 40}),
    ),
    "setup-node-in-images": (
        wc.image_job_installs_no_runtime,
        _append_step("images", {"uses": "actions/setup-node@" + "0" * 40}),
    ),
    "pip-in-images": (wc.image_job_installs_no_runtime, _last_run("images", "\npip install x")),
    "unpinned-action": (wc.actions_pinned, _step("backend", 0, "uses", "actions/checkout@v7")),
    "write-token": (wc.read_only_token, _set(["permissions"], {"contents": "write"})),
    "persisted-credentials": (
        wc.checkout_without_credentials,
        _step("backend", 0, "with", {"fetch-depth": 0}),
    ),
}


@pytest.mark.parametrize("case_id", sorted(CONTRASTS))
def test_k05_check_fails_on_a_one_change_fixture(case_id: str) -> None:
    check, change = CONTRASTS[case_id]
    flow = workflow()
    assert check(flow) == [], f"{case_id}: the repository's workflow must pass first"
    assert check(change(flow)) != [], case_id


def test_k07_secret_in_workflow_env_fails() -> None:
    flow = _step("backend", -1, "env", {"TOKEN_X": "${{ secrets.X }}"})(workflow())
    assert wc.no_secrets(flow, {"APP_DB_PASSWORD"}) != []
