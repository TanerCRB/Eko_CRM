"""Checks on the workflow files for the release path (EKO-1-15; ADR-0004-C30, C31, K-02..K-04).

Each returns the violations it finds, empty when the rule holds. `flows` maps a workflow file's
name to its parsed YAML (PyYAML reads the bare key `on` as True).
"""

import copy
import re
from typing import Any

from tests.support.workflow_checks import (
    RECORD_JOBS,
    RECORD_TOKEN,
    failures_fail_the_run,
    timeout_masked,
)

Workflow = dict[Any, Any]
RELEASE_FILE = "release.yml"
PUBLISH_JOB = "publish"
ADMISSION_JOB = "admission"
ADMITTED = "needs.admission.outputs.admitted == 'true'"
RELEASE_TAGS = {"push": {"tags": ["v*"]}}
# Status functions and alternation let a job run although a job it needs failed or was skipped.
STATUS_OVERRIDE = re.compile(r"\b(always|failure|cancelled)\s*\(|\|\|")
LOGIN = re.compile(r"\bdocker\s+login\b|login-action")
EXPRESSION = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
LOGIN_EXPRESSIONS = {"github.token", "github.actor"}
MISSING = object()


def triggers(flow: Workflow) -> Any:
    return flow.get("on", flow.get(True))


def effective_permissions(flow: Workflow, job: dict[str, Any]) -> Any:
    """A job's token permissions: its own key, else the workflow's, else MISSING (the repository
    default, which may grant write)."""
    if "permissions" in job:
        return job["permissions"]
    return flow.get("permissions", MISSING)


def holds_packages_write(permissions: Any) -> bool:
    if permissions is MISSING or permissions == "write-all":
        return True
    if isinstance(permissions, dict):
        return bool(permissions.get("packages") == "write")
    return bool(permissions != "read-all")


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs") or []
    return [needs] if isinstance(needs, str) else [str(n) for n in needs]


def admission_guard_violations(job: dict[str, Any]) -> list[str]:
    problems = []
    if ADMISSION_JOB not in _needs(job):
        problems.append("does not need the admission job")
    condition = str(job.get("if", ""))
    if ADMITTED not in condition:
        problems.append(f"is not conditioned on {ADMITTED}")
    if STATUS_OVERRIDE.search(condition):
        problems.append(f"condition {condition!r} can run past a failed or skipped job")
    return problems


def registry_write_violations(flows: dict[str, Workflow]) -> list[str]:
    """ADR-0004-C30: only the release workflow's publish job holds `packages: write`, behind the
    admission; a job or workflow with no `permissions` key counts as holding it."""
    problems = []
    for file, flow in sorted(flows.items()):
        for name, job in (flow.get("jobs") or {}).items():
            if not holds_packages_write(effective_permissions(flow, job)):
                continue
            if (file, name) != (RELEASE_FILE, PUBLISH_JOB):
                problems.append(f"{file}: job {name} holds packages: write")
                continue
            problems += [f"{file}: job {name} {p}" for p in admission_guard_violations(job)]
    return problems


def release_trigger_violations(flow: Workflow) -> list[str]:
    on = triggers(flow)
    if on != RELEASE_TAGS:
        return [f"release workflow triggers {on!r}, not only a push of a v* tag"]
    return []


def _login_steps(flow: Workflow) -> list[tuple[str, dict[str, Any]]]:
    return [
        (name, step)
        for name, job in (flow.get("jobs") or {}).items()
        for step in job.get("steps") or []
        if LOGIN.search(str(step.get("run", ""))) or LOGIN.search(str(step.get("uses", "")))
    ]


def registry_login_violations(flows: dict[str, Workflow]) -> list[str]:
    """ADR-0004-C30: a registry login takes no credential other than the run's GITHUB_TOKEN."""
    problems = []
    for file, flow in sorted(flows.items()):
        for name, step in _login_steps(flow):
            text = " ".join(
                str(part) for part in (step.get("run"), step.get("with"), step.get("env"))
            )
            for expression in EXPRESSION.findall(text):
                if expression not in LOGIN_EXPRESSIONS:
                    problems.append(f"{file}: job {name} logs in with {expression!r}")
            if "secrets." in text:
                problems.append(f"{file}: job {name} logs in with a stored secret")
    return problems


# K-02 (ADR-0004-C31): one build, checked, then pushed as checked ------------------------------

IMAGES_JOB = "images"
RUNTIME_JOB = "runtime"
CHECK_JOBS = ("admission", "backend", "frontend", IMAGES_JOB, RUNTIME_JOB)
PROJECT_IMAGES = ("backend", "frontend", "proxy", "backup")
BUILD = re.compile(
    r"\bdocker\s+(?:buildx\s+)?(?:image\s+)?build\b|\bcompose\b[^\n]*\bbuild\b|--build\b"
    r"|build-push-action|\bbuildah\b|\bkaniko\b|\bbake\b"
)
IDENTITY = "scripts/release-images.sh check-identity"
PUSH = "scripts/release-images.sh push"
DIGESTS_FILE = "$RUNNER_TEMP/digests.env"
PULLED = "scripts/release-images.sh pulled-digests"
RENDER = "release_composition render"


def checked(name: str) -> str:
    return f"eko-crm/{name}:checked"


def _steps_of(flow: Workflow, job: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = ((flow.get("jobs") or {}).get(job) or {}).get("steps") or []
    return steps


def _runs(flow: Workflow, job: str) -> list[str]:
    return [str(step.get("run", "")) for step in _steps_of(flow, job)]


def _index(flow: Workflow, job: str, needle: str) -> int:
    for index, run in enumerate(_runs(flow, job)):
        if needle in run:
            return index
    return -1


def build_once_violations(flow: Workflow) -> list[str]:
    problems = []
    for job in flow.get("jobs") or {}:
        for step in _steps_of(flow, job):
            text = f"{step.get('run', '')} {step.get('uses', '')}"
            for match in BUILD.finditer(text):
                if job != IMAGES_JOB or not match.group(0).startswith("docker"):
                    problems.append(f"{job}: builds an image ({match.group(0)!r})")
    builds = " ".join(_runs(flow, IMAGES_JOB))
    for name in PROJECT_IMAGES:
        made = re.findall(rf"docker build -t {re.escape(checked(name))} (\S+)", builds)
        if made != [name]:
            problems.append(f"{IMAGES_JOB}: {name} is built {len(made)} times, not once")
    if len(BUILD.findall(builds)) != len(PROJECT_IMAGES):
        problems.append(f"{IMAGES_JOB}: builds other than the four project images")
    image_check = [r for r in _runs(flow, IMAGES_JOB) if "scripts/image-check.sh" in r]
    if len(image_check) != 1 or not all(checked(n) in image_check[0] for n in PROJECT_IMAGES):
        problems.append(f"{IMAGES_JOB}: the image checks do not run on every checked image")
    tests = [s for s in _steps_of(flow, RUNTIME_JOB) if "pytest" in str(s.get("run", ""))]
    if not tests:
        problems.append(f"{RUNTIME_JOB}: runs no runtime tests")
    for step in tests:
        given = str((step.get("env") or {}).get("EKO_CHECKED_IMAGES", "")).split()
        if not all(f"{name}={checked(name)}" in given for name in PROJECT_IMAGES):
            problems.append(f"{RUNTIME_JOB}: the runtime tests are not given the checked images")
    for job, use in ((RUNTIME_JOB, "pytest"), (PUBLISH_JOB, PUSH)):
        identity, loads = _index(flow, job, IDENTITY), _index(flow, job, "docker load")
        if identity < 0 or loads < 0 or loads > identity:
            problems.append(f"{job}: does not load the checked images and check their identity")
        if _index(flow, job, use) < identity:
            problems.append(f"{job}: uses the images before checking their identity")
    runs = _runs(flow, PUBLISH_JOB)
    push, render = _index(flow, PUBLISH_JOB, PUSH), _index(flow, PUBLISH_JOB, RENDER)
    if push < 0 or f'> "{DIGESTS_FILE}"' not in runs[push]:
        problems.append(f"{PUBLISH_JOB}: the pushes do not record their digests")
    if render < push or f'--digests "{DIGESTS_FILE}"' not in runs[render]:
        problems.append(f"{PUBLISH_JOB}: the composition is not rendered from the pushes' digests")
    return problems


def _expression(text: Any) -> str:
    return str(text or "").replace(" ", "")


def third_party_digest_violations(flow: Workflow) -> list[str]:
    """K-02: the composition's postgres and keycloak digests are those the runtime tests pulled."""
    steps = _steps_of(flow, RUNTIME_JOB)
    recorders = [i for i, s in enumerate(steps) if PULLED in str(s.get("run", ""))]
    if len(recorders) != 1 or recorders[0] < _index(flow, RUNTIME_JOB, "pytest"):
        return [f"{RUNTIME_JOB}: does not record the pulled digests after the runtime tests"]
    step_id = steps[recorders[0]].get("id")
    outputs = ((flow.get("jobs") or {}).get(RUNTIME_JOB) or {}).get("outputs") or {}
    render = [s for s in _steps_of(flow, PUBLISH_JOB) if RENDER in str(s.get("run", ""))]
    problems = []
    for name in ("postgres", "keycloak"):
        if _expression(outputs.get(name)) != f"${{{{steps.{step_id}.outputs.{name}}}}}":
            problems.append(f"{RUNTIME_JOB}: output {name} is not the recorded pulled digest")
        variable = f"{name.upper()}_DIGEST"
        wired = [
            s
            for s in render
            if _expression((s.get("env") or {}).get(variable))
            == f"${{{{needs.{RUNTIME_JOB}.outputs.{name}}}}}"
            and f'--{name} "${variable}"' in str(s.get("run", ""))
        ]
        if len(render) != 1 or not wired:
            problems.append(f"{PUBLISH_JOB}: the {name} digest is not the runtime tests' one")
    return problems


# R-01 (K-04, K-05): a partial re-run reuses the admission job's outputs, so publish decides again

READMIT = "uv run python -m tests.support.releases admit"
READMIT_TAG = 'grep -qxF "tag=$RELEASE_TAG"'
TAG_COMMIT = (
    'uv run python -m tests.support.releases tag-commit --tag "$RELEASE_TAG" --commit "$GITHUB_SHA"'
)
READMIT_ENV = {
    RECORD_TOKEN: "${{ github.token }}",
    "RELEASE_REPO_TOKEN": "${{ github.token }}",
    "RELEASE_TAG": "${{ needs.admission.outputs.tag }}",
}


def publish_readmission_violations(flow: Workflow) -> list[str]:
    """Before the registry login and the push, the publish job runs the admission again and
    checks that the tag still names this run's commit; the step cannot be skipped or ignored."""
    steps = _steps_of(flow, PUBLISH_JOB)
    found = [i for i, s in enumerate(steps) if READMIT in str(s.get("run", ""))]
    if len(found) != 1:
        return [f"{PUBLISH_JOB}: does not decide the admission again"]
    index, step = found[0], steps[found[0]]
    problems = []
    run = str(step.get("run", ""))
    if READMIT_TAG not in run:
        problems.append(f"{PUBLISH_JOB}: the admission decided again is not compared by tag")
    if TAG_COMMIT not in run:
        problems.append(f"{PUBLISH_JOB}: does not check the tag still names this run's commit")
    if step.get("shell") != "bash":
        problems.append(f"{PUBLISH_JOB}: the admission step does not stop on a failed command")
    if "if" in step or "continue-on-error" in step:
        problems.append(f"{PUBLISH_JOB}: the admission step can be skipped or ignored")
    env = step.get("env") or {}
    if any(env.get(k) != v for k, v in READMIT_ENV.items()):
        problems.append(f"{PUBLISH_JOB}: the admission step is not given {sorted(READMIT_ENV)}")
    pushes = [
        i
        for i, s in enumerate(steps)
        if LOGIN.search(str(s.get("run", ""))) or PUSH in str(s.get("run", ""))
    ]
    if not pushes or min(pushes) < index:
        problems.append(f"{PUBLISH_JOB}: logs in or pushes before deciding the admission again")
    checkout = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    if not checkout or (checkout[0].get("with") or {}).get("fetch-depth") != 0:
        problems.append(f"{PUBLISH_JOB}: its checkout has no full history for reachability")
    return problems


# K-03: publishing only after every check, none of which can pass without running ---------------


def _closure(flow: Workflow, job: str) -> set[str]:
    jobs = flow.get("jobs") or {}
    seen: set[str] = set()
    todo = _needs(jobs.get(job) or {})
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo += _needs(jobs.get(name) or {})
    return seen


def publish_dependency_violations(flow: Workflow) -> list[str]:
    missing = set(CHECK_JOBS) - _closure(flow, PUBLISH_JOB)
    return [f"{PUBLISH_JOB}: does not depend on {name}" for name in sorted(missing)]


def check_masking_violations(flow: Workflow) -> list[str]:
    problems = failures_fail_the_run(flow)
    jobs = flow.get("jobs") or {}
    for name in CHECK_JOBS:
        job = jobs.get(name)
        if job is None:
            problems.append(f"no {name} job")
            continue
        if "if" in job:
            problems.append(f"{name}: a check job with a condition can be skipped")
        problems += [
            f"{name}: step {s.get('name')!r} has a condition"
            for s in job.get("steps") or []
            if "if" in s
        ]
    publish = jobs.get(PUBLISH_JOB) or {}
    problems += [f"{PUBLISH_JOB}: {p}" for p in admission_guard_violations(publish)]
    return problems


# K-07: the existing ci.yml against its base -----------------------------------------------------

READ_RECORD = {"packages": "read"}
# The differences K-07 allows, each one listed (gate-1 K-07; C-4 of #56); anything else is red.
# RECORD_JOBS (workflow_checks) is the closed list of jobs these differences may touch.
RECORD_ENV = (RECORD_TOKEN, "${{ github.token }}")
CI_LOGIN_STEP: dict[str, Any] = {
    "name": "Registry login, read only (pulls the previous release's backend)",
    "shell": "bash",
    "env": {"TOKEN": "${{ github.token }}", "ACTOR": "${{ github.actor }}"},
    "run": 'printf \'%s\' "$TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin',
}
CI_RUNTIME_RUN = 'uv run pytest -m "runtime or previous_release" tests/runtime -v'
CI_COMPAT_RUN = "uv run python -m tests.support.openapi_compat --from-record"
# (job, the step's run at the base) -> the run allowed at the head.
ALLOWED_RUNS = {
    ("runtime", "uv run pytest -m runtime tests/runtime -v"): CI_RUNTIME_RUN,
    ("backend", "uv run python -m tests.support.openapi_compat"): CI_COMPAT_RUN,
}
FULL_HISTORY_JOBS = ("runtime",)


def _revert_allowed(name: str, job: dict[str, Any]) -> dict[str, Any]:
    """The job with each allowed difference undone. Both sides are undone, so the comparison
    holds while this change is the change set and once it is on the base (QA F-1)."""
    reverted = copy.deepcopy({k: v for k, v in job.items() if k != "permissions"})
    if name not in RECORD_JOBS:
        return reverted
    steps: list[dict[str, Any]] = list(reverted.get("steps") or [])
    if CI_LOGIN_STEP in steps:
        steps.remove(CI_LOGIN_STEP)
    for step in steps:
        options = step.get("with") or {}
        if (
            name in FULL_HISTORY_JOBS
            and str(step.get("uses", "")).startswith("actions/checkout@")
            and options.get("fetch-depth") == 0
        ):
            del options["fetch-depth"]
        for (job_name, old), new in ALLOWED_RUNS.items():
            if job_name == name and step.get("run") == new:
                step["run"] = old
                env = step.get("env") or {}
                if env.get(RECORD_ENV[0]) == RECORD_ENV[1]:
                    del env[RECORD_ENV[0]]
                    if not env:
                        step.pop("env")
    reverted["steps"] = steps
    return reverted


def ci_unchanged_violations(base: Workflow, head: Workflow) -> list[str]:
    """Every base job is present and identical but for the differences listed above and a
    retuned `timeout-minutes` value (workflow_checks.timeout_masked); its permissions may gain
    `packages: read` on a record-reading job only; the workflow's own keys are identical."""
    problems = []
    for key in sorted(set(base) | set(head), key=str):
        if key != "jobs" and base.get(key) != head.get(key):
            problems.append(f"workflow key {key!r} changed")
    head_jobs = head.get("jobs") or {}
    for name, job in (base.get("jobs") or {}).items():
        now = head_jobs.get(name)
        if now is None:
            problems.append(f"job {name} removed")
            continue
        if timeout_masked(_revert_allowed(name, job)) != timeout_masked(_revert_allowed(name, now)):
            problems.append(f"job {name}: changed")
        before, after = effective_permissions(base, job), effective_permissions(head, now)
        allowed = [before]
        if name in RECORD_JOBS and isinstance(before, dict):
            allowed.append({**before, **READ_RECORD})
        if after not in allowed:
            problems.append(f"job {name}: permissions {after!r}, not {before!r} + packages: read")
    return problems
