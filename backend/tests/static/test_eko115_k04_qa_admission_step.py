"""EKO-1-15 K-04, added by QA: the release workflow's admission step is what makes the run
admitted. The admission function is proven on fixture events elsewhere; here the step's literal
script runs as GitHub runs `shell: bash` (`bash --noprofile --norc -eo pipefail`), so a step that
writes `admitted=true` without the admission deciding it is red.

The admission command is replaced by a stand-in `uv` on PATH that answers as the command would
(exit 0 with `tag=`, 1 refused, 2 cannot tell); one case runs the real command on an event it
refuses before any registry call.
"""

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support.repo import REPO_ROOT, bash

RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"
GITHUB_BASH = ["--noprofile", "--norc", "-eo", "pipefail"]
# The stand-in directory first on PATH; Git Bash on Windows needs it as /c/..., not C:/...
WITH_STAND_IN = (
    'PATH="$(cygpath -u "$EKO_QA_STAND_IN" 2>/dev/null || printf %s "$EKO_QA_STAND_IN")'
    ':$PATH"; . "$0"'
)


def admission_job() -> tuple[dict[str, Any], dict[str, Any]]:
    flow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    job = flow["jobs"]["admission"]
    [step] = [s for s in job["steps"] if s.get("id") == "admit"]
    return job, step


def run_step(
    tmp_path: Path, event: dict[str, str], answer: tuple[int, str] | None
) -> tuple[int, str, str]:
    """The admit step's script; `answer` = the stand-in `uv`'s exit code and its `|`-separated
    output lines, or None for the real command."""
    _, step = admission_job()
    assert step.get("shell") == "bash"
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8", newline="\n")
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_OUTPUT": output.as_posix(),
        "RELEASE_RECORD_TOKEN": "not-a-real-token",
        **event,
    }
    if answer is not None:
        stand_in = tmp_path / "bin"
        stand_in.mkdir()
        code, text = answer
        uv = stand_in / "uv"
        lines = " ".join(shlex.quote(line) for line in text.split("|"))
        uv.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' {lines}\nexit {code}\n", newline="\n")
        uv.chmod(0o755)
        env["EKO_QA_STAND_IN"] = stand_in.as_posix()
        command = [bash(), *GITHUB_BASH, "-c", WITH_STAND_IN, script.as_posix()]
    else:
        command = [bash(), *GITHUB_BASH, script.as_posix()]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT / step["working-directory"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return result.returncode, output.read_text(encoding="utf-8"), result.stdout + result.stderr


def tag_push(actor: str = "TanerCRB") -> dict[str, str]:
    return {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/tags/v1.3.0",
        "GITHUB_REF_NAME": "v1.3.0",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_ACTOR": actor,
        "GITHUB_TRIGGERING_ACTOR": actor,
    }


def test_eko115_k04_qa_admission_output_is_the_admit_steps() -> None:
    job, _ = admission_job()
    assert job["outputs"]["admitted"] == "${{ steps.admit.outputs.admitted }}"
    assert job["outputs"]["tag"] == "${{ steps.admit.outputs.tag }}"


def test_eko115_k04_qa_admitted_command_admits_the_run(tmp_path: Path) -> None:
    answer = (0, "releases admit: v1.3.0: admitted|tag=v1.3.0")
    code, output, log = run_step(tmp_path, tag_push(), answer)
    assert code == 0, log
    assert output.splitlines() == ["tag=v1.3.0", "admitted=true"], output


@pytest.mark.parametrize(
    "answer",
    [(1, "releases admit: v1.3.0: pushed by an account that may not publish"), (2, "x")],
    ids=["refused", "cannot-tell"],
)
def test_eko115_k04_qa_contrast_a_refusing_command_admits_nothing(
    tmp_path: Path, answer: tuple[int, str]
) -> None:
    code, output, log = run_step(tmp_path, tag_push(), answer)
    assert code != 0, log
    assert "admitted=true" not in output and "tag=" not in output, output


def test_eko115_k04_qa_the_real_command_refuses_another_account(tmp_path: Path) -> None:
    # Refused on the account before the record is read: no registry call is made.
    code, output, log = run_step(tmp_path, tag_push(actor="someone-else"), None)
    assert code == 1, log
    assert "admitted=true" not in output and "tag=" not in output, output
    assert "may not publish" in log, log
