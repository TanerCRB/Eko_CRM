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


# Retuning an existing job's time bound (EKO-1-20, #76) ------------------------------------------
# The checks that compare existing jobs to their base do not report a job whose only difference
# is the integer value of its own `timeout-minutes`, or the one comment line directly above that
# key. Adding the key to a job, removing it, or setting it to anything but an integer is still a
# changed job: both sides are masked alike, so a key present on one side only stays a difference.

TIMEOUT_KEY = "timeout-minutes"
TIMEOUT_MASK = "<retuned>"
TIMEOUT_LINE = re.compile(r"    timeout-minutes: \d+")
JOB_COMMENT = re.compile(r"    #.*")


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def timeout_masked(job: Any) -> Any:
    """The job with an integer `timeout-minutes` replaced by one mask, for comparison only."""
    if not isinstance(job, dict) or not _integer(job.get(TIMEOUT_KEY)):
        return job
    return {**job, TIMEOUT_KEY: TIMEOUT_MASK}


def timeout_lines_masked(block: str) -> str:
    """A job's lines in the file with its `timeout-minutes` line masked and the one comment line
    directly above it dropped, for comparison only."""
    lines: list[str] = []
    for line in block.split("\n"):
        if TIMEOUT_LINE.fullmatch(line):
            if lines and JOB_COMMENT.fullmatch(lines[-1]):
                lines.pop()
            line = f"    {TIMEOUT_KEY}: {TIMEOUT_MASK}"
        lines.append(line)
    return "\n".join(lines)


# The keycloak pre-build step block (EKO-1-12 K-04, fix round 3, 2026-11-11) -------------------
# The text half of the same exact-listed tolerance release_workflow.CI_KEYCLOAK_PREBUILD_STEP
# gives the parsed half: the step's comment line and the step's own lines, as bytes. The mask
# drops the block once per side and only this byte-exact copy — a second copy, a byte different
# anywhere in it, is not the block and stays a difference.

CI_KEYCLOAK_PREBUILD_LINES: tuple[str, ...] = (
    (
        "      # EKO-1-12 fix-round-3 (2026-11-11): keycloak has no checked image "
        "(scripts/release-images.sh NAMES=backend frontend proxy backup; its digest "
        "integration is deferred to #118), so under EKO_CHECKED_IMAGES the session's "
        "first compose up built localhost/eko-crm/keycloak:26.8.1-eko112 after the "
        "K-04 snapshot (#135 run 130307698397); building it before the snapshot makes "
        "the session reuse the reference, and K-04 still flags every image whose name "
        "first appears during the session."
    ),
    "      - name: Build the keycloak composition image before the K-04 snapshot",
    "        shell: bash",
    "        run: |",
    '          bash scripts/dev-env.sh "$RUNNER_TEMP/keycloak-prebuild.env"',
    (
        "          docker compose -p eko-ci-keycloak-prebuild --env-file "
        '"$RUNNER_TEMP/keycloak-prebuild.env" --profile dev build keycloak'
    ),
)


def keycloak_prebuild_lines_masked(block: str) -> str:
    """A job's lines in the file with the exact keycloak pre-build block dropped once, for
    comparison only: applied to both sides, it holds while the step is the change set and once
    the step is on the base (the F-1 shape), and a second copy of the block is not dropped."""
    lines = block.split("\n")
    step = list(CI_KEYCLOAK_PREBUILD_LINES)
    kept: list[str] = []
    index = 0
    dropped = False
    while index < len(lines):
        if not dropped and lines[index : index + len(step)] == step:
            index += len(step)
            dropped = True
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept)
