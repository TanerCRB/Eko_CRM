"""EKO-1-35 K-04: the check runs in CI on every pull request and every push to `main`,
unconditionally, and its failure fails the job.

The check is the K-01..K-03 test modules inside the backend job's pytest step (G-1 A), so this
judges that step, the default test selection, and the modules' own text. Whether it actually ran
at a head SHA is read from that run's CI log (QA), not here.
"""

import copy
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support import frontend_contract as fc
from tests.support import workflow_checks as wc
from tests.support.api_surface import real_app
from tests.support.contract_tree import copied_tree, environment, run_check
from tests.support.repo import REPO_ROOT

CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BACKEND = REPO_ROOT / "backend"
CHECK_MODULES = (
    "tests/static/test_eko135_k01_frontend_types.py",
    "tests/static/test_eko135_k02_country_list.py",
    "tests/static/test_eko135_k03_export_coverage.py",
)
SUPPORT = ("tests/support/frontend_contract.py", "tests/support/contract_tree.py")
ALLOWED_FLAGS = frozenset({"-v", "-vv", "-q", "-ra", "-rA"})
Workflow = dict[Any, Any]


def workflow() -> Workflow:
    loaded: Workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    return loaded


def wiring_problems(flow: Workflow) -> list[str]:
    """The one backend pytest step: no condition, no mask, no narrowed selection, both triggers."""
    problems = []
    on = wc.triggers(flow)
    if "pull_request" not in on:
        problems.append("no pull_request trigger")
    elif {"paths", "paths-ignore", "branches", "types"} & set(on["pull_request"] or {}):
        problems.append("the pull_request trigger is filtered")
    if (on.get("push") or {}).get("branches") != ["main"]:
        problems.append("no push trigger on main")
    # The steps running the default selection, which holds the check; the runtime jobs select
    # `-m "runtime or previous_release"` and so never run it.
    found = [
        (job_id, job, step)
        for job_id, job in (flow.get("jobs") or {}).items()
        for step in job.get("steps") or []
        if str(step.get("run", "")).lstrip().startswith("uv run pytest")
        and step.get("working-directory") == "backend"
        and not {"-m", "-k"} & set(shlex.split(str(step["run"]).split("\n")[0]))
    ]
    if len(found) != 1:
        return [*problems, f"{len(found)} backend steps run the default selection, not one"]
    job_id, job, step = found[0]
    if "if" in job or job.get("continue-on-error"):
        problems.append(f"{job_id}: the job is conditional or may fail")
    if "changes" in str(job.get("needs", "")):
        problems.append(f"{job_id}: the job needs the changes job")
    if "if" in step or step.get("continue-on-error"):
        problems.append(f"{job_id}: the pytest step is conditional or may fail")
    if "PYTEST_ADDOPTS" in (step.get("env") or {}) or "PYTEST_ADDOPTS" in (job.get("env") or {}):
        problems.append(f"{job_id}: PYTEST_ADDOPTS changes the selection")
    run = str(step["run"]).strip()
    if wc.FAILURE_MASK.search(run) or "\n" in run:
        problems.append(f"{job_id}: the pytest step runs more than pytest, or masks its failure")
    words = shlex.split(run)
    if words[:3] != ["uv", "run", "pytest"] or not set(words[3:]) <= ALLOWED_FLAGS:
        problems.append(f"{job_id}: the pytest step selects tests ({run!r})")
    return problems


# Text that skips, expects failure of, or deselects a test: none of it is in a check module.
SKIPPING = (
    "mark.skip",
    "mark.xfail",
    "pytest.skip",
    "pytest.xfail",
    "importorskip",
    "mark.runtime",
    "mark.previous_release",
    "pytestmark",
)


def skip_problems(texts: dict[str, str]) -> list[str]:
    return [
        f"{path}: {word}"
        for path, text in sorted(texts.items())
        for word in SKIPPING
        if word in text
    ]


def test_eko135_k04_the_pytest_step_runs_unconditionally() -> None:
    assert wiring_problems(workflow()) == []


def _step(flow: Workflow) -> dict[str, Any]:
    steps = [
        s
        for s in flow["jobs"]["backend"]["steps"]
        if str(s.get("run", "")).startswith("uv run pytest")
    ]
    assert len(steps) == 1
    found: dict[str, Any] = steps[0]
    return found


def _set_step(key: str, value: Any) -> Any:
    def apply(flow: Workflow) -> None:
        _step(flow)[key] = value

    return apply


def _gated(flow: Workflow) -> None:
    flow["jobs"]["backend"]["needs"] = ["changes"]


def _job_if(flow: Workflow) -> None:
    flow["jobs"]["backend"]["if"] = wc.TRIGGER_CONDITION


def _no_push(flow: Workflow) -> None:
    wc.triggers(flow).pop("push")


def _filtered_pull_request(flow: Workflow) -> None:
    on = wc.triggers(flow)
    on["pull_request"] = {"paths": ["backend/**"]}


def _run(text: str) -> Any:
    def apply(flow: Workflow) -> None:
        _step(flow)["run"] = text

    return apply


def _addopts(flow: Workflow) -> None:
    step = _step(flow)
    step["env"] = {**(step.get("env") or {}), "PYTEST_ADDOPTS": "-k 'not eko135'"}


MUTATIONS = {
    "step-if-false": _set_step("if", "false"),
    "step-continue-on-error": _set_step("continue-on-error", True),
    "or-true": _run("uv run pytest -v || true"),
    "set-plus-e": _run("set +e\nuv run pytest -v"),
    "marker-selection": _run("uv run pytest -v -m runtime"),
    "keyword-deselection": _run("uv run pytest -v -k 'not eko135'"),
    "ignored-module": _run("uv run pytest -v --ignore=tests/static"),
    "addopts-in-env": _addopts,
    "job-needs-changes": _gated,
    "job-if": _job_if,
    "no-push-to-main": _no_push,
    "filtered-pull-request": _filtered_pull_request,
}


@pytest.mark.parametrize("case_id", sorted(MUTATIONS))
def test_eko135_k04_a_condition_or_mask_on_the_step_fails(case_id: str) -> None:
    flow = copy.deepcopy(workflow())
    MUTATIONS[case_id](flow)
    assert wiring_problems(flow) != [], case_id


def module_texts() -> dict[str, str]:
    return {path: (BACKEND / path).read_text(encoding="utf-8") for path in CHECK_MODULES + SUPPORT}


def test_eko135_k04_the_check_modules_carry_no_skip_or_selecting_marker() -> None:
    assert skip_problems(module_texts()) == []


SKIPS = {
    "skip-mark": "@pytest.mark.skip(reason='later')\n",
    "skipif-mark": "@pytest.mark.skipif(True, reason='x')\n",
    "xfail-mark": "@pytest.mark.xfail\n",
    "skip-call": "    pytest.skip('frontend/ is absent')\n",
    "importorskip": "pytest.importorskip('x')\n",
    "runtime-marker": "pytestmark = pytest.mark.runtime\n",
    "previous-release-marker": "@pytest.mark.previous_release\n",
}


@pytest.mark.parametrize("case_id", sorted(SKIPS))
def test_eko135_k04_a_skip_or_marker_in_a_check_module_fails(case_id: str) -> None:
    texts = module_texts()
    texts[CHECK_MODULES[0]] += SKIPS[case_id]
    assert skip_problems(texts) != [], case_id


def test_eko135_k04_the_default_selection_collects_every_check_module() -> None:
    env = {k: v for k, v in environment().items() if k != "PYTEST_ADDOPTS"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
        + list(CHECK_MODULES),
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=300,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "deselected" not in output, output
    for module in CHECK_MODULES:
        assert f"{module}::" in output.replace("\\", "/"), module


# A checkout without `frontend/` fails rather than skips -----------------------------------------


def test_eko135_k04_no_frontend_sources_fail() -> None:
    assert fc.findings({}, real_app().openapi()) != []


def test_eko135_k04_a_tree_without_frontend_fails_the_command(tmp_path: Path) -> None:
    tree = copied_tree(tmp_path, {})
    shutil.rmtree(tree / "frontend")
    assert fc.api_sources(tree) == {}
    result = run_check(tree)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "nothing was checked" in result.stdout
