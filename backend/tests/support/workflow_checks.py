"""K-05 checks on the CI workflow: each returns its violations, empty when it holds."""

import re
from typing import Any

SHA_PIN = re.compile(r"[^@\s]+@[0-9a-f]{40}")
RUNTIME_SETUP_ACTIONS = re.compile(
    r"(actions/setup-python|actions/setup-node|astral-sh/setup-uv|pnpm/action-setup|setup-java)"
)
RUNTIME_INSTALL = re.compile(
    r"(apt(-get)?\s+install[^\n]*(python|node))|(\b(uv|pip|pipx|npm|pnpm|npx|yarn|nvm)\s)"
    r"|(\bpython3?\s)|(\bnode\s)"
)
FAILURE_MASK = re.compile(r"\|\|\s*(true|:)\b|\bset\s+\+e\b|exit\s+0\s*$", re.MULTILINE)
CONDITIONAL_JOBS = ("images", "runtime")
ALWAYS_JOBS = ("backend", "frontend")
TRIGGER_CONDITION = "needs.changes.outputs.runtime == 'true'"

Workflow = dict[Any, Any]


def triggers(workflow: Workflow) -> dict[str, Any]:
    # PyYAML reads the bare key `on` as the boolean True.
    on: dict[str, Any] = workflow.get("on", workflow.get(True)) or {}
    return on


def _steps(workflow: Workflow) -> list[tuple[str, dict[str, Any]]]:
    return [
        (job_id, step)
        for job_id, job in workflow.get("jobs", {}).items()
        for step in job.get("steps", [])
    ]


def actions_pinned(workflow: Workflow) -> list[str]:
    return [
        f"{job}: {step['uses']} is not pinned to a commit SHA"
        for job, step in _steps(workflow)
        if "uses" in step and not SHA_PIN.fullmatch(step["uses"])
    ]


RECORD_TOKEN = "RELEASE_RECORD_TOKEN"
# The closed list of ci.yml jobs that may read the release record (EKO-1-15 C-3, C-7, C-8;
# runtime-checked: EKO-1-19 G-6 A, the release-mode runtime job);
# K-07's check on ci.yml uses the same list.
RECORD_JOBS = ("backend", "runtime", "runtime-checked")


def reads_release_record(job: dict[str, Any]) -> bool:
    """EKO-1-15: a job reads the release record when one of its steps is given the record token."""
    return any(RECORD_TOKEN in (step.get("env") or {}) for step in job.get("steps", []))


def read_only_token(workflow: Workflow) -> list[str]:
    """Read-only token: `contents: read`, plus `packages: read` only on a job of RECORD_JOBS that
    reads the release record (EKO-1-15 C-3, C-8, exception EKO-1-15/weakening-1)."""
    problems = []
    if workflow.get("permissions") != {"contents": "read"}:
        problems.append(f"workflow permissions {workflow.get('permissions')!r}")
    for job_id, job in workflow.get("jobs", {}).items():
        permissions = job.get("permissions")
        allowed = [{"contents": "read"}]
        if job_id in RECORD_JOBS and reads_release_record(job):
            allowed.append({"contents": "read", "packages": "read"})
        if permissions is not None and permissions not in allowed:
            problems.append(f"{job_id}: permissions {permissions!r}")
    return problems


def checkout_without_credentials(workflow: Workflow) -> list[str]:
    return [
        f"{job}: checkout keeps credentials"
        for job, step in _steps(workflow)
        if str(step.get("uses", "")).startswith("actions/checkout@")
        and (step.get("with") or {}).get("persist-credentials") is not False
    ]


def image_job_installs_no_runtime(workflow: Workflow) -> list[str]:
    """ADR-0001-C4: the image-build job sets up neither Python nor Node.js on the runner."""
    job = workflow.get("jobs", {}).get("images")
    if job is None:
        return ["no images job"]
    problems = []
    for step in job.get("steps", []):
        if RUNTIME_SETUP_ACTIONS.search(str(step.get("uses", ""))):
            problems.append(f"images: {step['uses']}")
        if RUNTIME_INSTALL.search(str(step.get("run", ""))):
            problems.append(f"images: step {step.get('name')!r} runs a Python or Node.js tool")
    if not any("docker build" in str(step.get("run", "")) for step in job.get("steps", [])):
        problems.append("images: no docker build")
    return problems


def failures_fail_the_run(workflow: Workflow) -> list[str]:
    problems = []
    for job_id, job in workflow.get("jobs", {}).items():
        if job.get("continue-on-error"):
            problems.append(f"{job_id}: continue-on-error")
        for step in job.get("steps", []):
            if step.get("continue-on-error"):
                problems.append(f"{job_id}: step {step.get('name')!r} continue-on-error")
            if FAILURE_MASK.search(str(step.get("run", ""))):
                problems.append(f"{job_id}: step {step.get('name')!r} masks a failure")
    return problems


def job_conditions(workflow: Workflow) -> list[str]:
    """Every PR runs the unit and static jobs; the runtime ones run by job condition only."""
    problems = []
    on = triggers(workflow)
    if "pull_request" not in on:
        problems.append("no pull_request trigger")
    elif {"paths", "paths-ignore", "branches"} & set(on["pull_request"] or {}):
        problems.append("pull_request trigger is filtered")
    if (on.get("push") or {}).get("branches") != ["main"]:
        problems.append("push trigger is not main")
    jobs = workflow.get("jobs", {})
    for name in ALWAYS_JOBS:
        if name not in jobs:
            problems.append(f"no {name} job")
        elif "if" in jobs[name]:
            problems.append(f"{name}: conditional")
    for name in CONDITIONAL_JOBS:
        job = jobs.get(name, {})
        if job.get("if") != TRIGGER_CONDITION or "changes" not in str(job.get("needs")):
            problems.append(f"{name}: not conditioned on the changes job")
    decide = " ".join(str(s.get("run", "")) for s in jobs.get("changes", {}).get("steps", []))
    if "scripts/ci-runtime-trigger.sh decide" not in decide:
        problems.append("changes: does not decide with scripts/ci-runtime-trigger.sh")
    return problems


def no_secrets(workflow: Workflow, secret_names: set[str]) -> list[str]:
    problems = []
    blocks = [("workflow", workflow.get("env") or {})]
    for job_id, job in workflow.get("jobs", {}).items():
        blocks.append((job_id, job.get("env") or {}))
        blocks += [(job_id, step.get("env") or {}) for step in job.get("steps", [])]
    for where, env in blocks:
        for key, value in env.items():
            if key in secret_names or "secrets." in str(value):
                problems.append(f"{where}: env {key} carries a secret")
    return problems
