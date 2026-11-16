"""EKO-1-19 QA (K-03, K-04 wiring): every step of the two release-mode jobs runs whenever its job
runs. A step-level `if:` can switch off the image check, the identity check after the tests or
the tests themselves while the job, and the PR, stay green; the release-mode check accepted
such a step (QA mutation EKO-1-19-M13).
"""

import copy
from typing import Any

import pytest
import yaml

from tests.support import release_mode_ci as rm
from tests.support.repo import REPO_ROOT

Workflow = dict[Any, Any]


def ci() -> Workflow:
    loaded: Workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    return loaded


def conditional_steps(flow: Workflow) -> list[str]:
    return [
        f"{job}: step {index} ({step.get('name') or step.get('uses')!r}) has if: {step['if']!r}"
        for job in (rm.BUILD_JOB, rm.RELEASE_MODE_JOB)
        for index, step in enumerate(flow["jobs"][job].get("steps") or [])
        if "if" in step
    ]


def test_eko119_qa_release_mode_steps_are_unconditional() -> None:
    assert conditional_steps(ci()) == []


@pytest.mark.parametrize(
    "needle",
    [rm.SESSION_CHECK, "pytest", "docker load", rm.SNAPSHOT, "docker build"],
    ids=["session-check", "tests", "load", "snapshot", "build"],
)
def test_eko119_qa_a_step_switched_off_by_if_is_found(needle: str) -> None:
    flow = copy.deepcopy(ci())
    job = rm.BUILD_JOB if needle == "docker build" else rm.RELEASE_MODE_JOB
    rm._step(flow, job, needle)[1]["if"] = False
    assert conditional_steps(flow) != []
