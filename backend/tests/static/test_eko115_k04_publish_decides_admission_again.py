"""EKO-1-15 K-04/K-05, Reviewer R-01: a partial re-run ("Re-run failed jobs") reuses the admission
job's outputs, so the publish job decides the admission again before any push: the account
(pusher and re-runner), the order against published releases, the tag not yet published (by
`releases admit`), and the tag still naming this run's commit (`releases tag-commit`). A refusal
or a cannot-tell stops the job before the registry login and the push.
"""

import copy
import io
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.test_eko115_k04_qa_admission_step import GITHUB_BASH, WITH_STAND_IN
from tests.support import release_workflow as rw
from tests.support import releases
from tests.support.releases import CannotTell, GitHubTags, Response
from tests.support.repo import REPO_ROOT, bash

RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"
Workflow = dict[Any, Any]
SHA = "a" * 40
OTHER = "d" * 40
TAG_OBJECT = "e" * 40


def flow() -> Workflow:
    loaded: Workflow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    return loaded


def _readmit_index(f: Workflow) -> int:
    steps = f["jobs"]["publish"]["steps"]
    found = [i for i, s in enumerate(steps) if "tests.support.releases admit" in str(s.get("run"))]
    assert len(found) == 1, found
    return found[0]


# The workflow's wiring -----------------------------------------------------------------------


def test_eko115_k04_publish_decides_the_admission_again_before_any_push() -> None:
    assert rw.publish_readmission_violations(flow()) == []


def _drop_readmission(f: Workflow) -> Workflow:
    f["jobs"]["publish"]["steps"].pop(_readmit_index(f))
    return f


def _after_the_push(f: Workflow) -> Workflow:
    steps = f["jobs"]["publish"]["steps"]
    steps.append(steps.pop(_readmit_index(f)))
    return f


def _between_login_and_push(f: Workflow) -> Workflow:
    steps = f["jobs"]["publish"]["steps"]
    step = steps.pop(_readmit_index(f))
    login = [i for i, s in enumerate(steps) if "docker login" in str(s.get("run"))][0]
    steps.insert(login + 1, step)
    return f


def _readmit_run(old: str, new: str) -> Any:
    def apply(f: Workflow) -> Workflow:
        step = f["jobs"]["publish"]["steps"][_readmit_index(f)]
        assert old in step["run"], old
        step["run"] = step["run"].replace(old, new)
        return f

    return apply


def _readmit_key(key: str, value: Any) -> Any:
    def apply(f: Workflow) -> Workflow:
        f["jobs"]["publish"]["steps"][_readmit_index(f)][key] = value
        return f

    return apply


def _shallow(f: Workflow) -> Workflow:
    f["jobs"]["publish"]["steps"][0]["with"].pop("fetch-depth")
    return f


PLANTS = {
    "no-readmission": _drop_readmission,
    "readmission-after-the-push": _after_the_push,
    "readmission-after-the-login": _between_login_and_push,
    "tag-not-compared": _readmit_run('grep -qxF "tag=$RELEASE_TAG"', "true"),
    "no-tag-commit-check": _readmit_run("tests.support.releases tag-commit", "true"),
    "step-condition": _readmit_key("if", "false"),
    "continue-on-error": _readmit_key("continue-on-error", True),
    "not-bash": _readmit_key("shell", "sh"),
    "no-record-token": _readmit_key("env", {"RELEASE_TAG": "x", "RELEASE_REPO_TOKEN": "x"}),
    "shallow-checkout": _shallow,
}


@pytest.mark.parametrize("case_id", sorted(PLANTS))
def test_eko115_k04_readmission_check_fails_on_a_plant(case_id: str) -> None:
    assert rw.publish_readmission_violations(PLANTS[case_id](copy.deepcopy(flow()))) != []


# The step's literal script, as GitHub runs `shell: bash` -------------------------------------


def run_readmission(tmp_path: Path, admit: tuple[int, str], tag_commit: int) -> tuple[int, str]:
    """The step's script with a stand-in `uv`: `admit` answers (exit, `|`-separated lines),
    `tag-commit` answers its exit code."""
    step = flow()["jobs"]["publish"]["steps"][_readmit_index(flow())]
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8", newline="\n")
    stand_in = tmp_path / "bin"
    stand_in.mkdir()
    code, text = admit
    lines = " ".join(shlex.quote(line) for line in text.split("|"))
    uv = stand_in / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'case "$5" in\n'
        f"  admit) printf '%s\\n' {lines}; exit {code} ;;\n"
        f"  tag-commit) exit {tag_commit} ;;\n"
        "esac\nexit 99\n",
        newline="\n",
    )
    uv.chmod(0o755)
    env = {
        **os.environ,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "RELEASE_TAG": "v1.3.0",
        "GITHUB_SHA": SHA,
        "EKO_QA_STAND_IN": stand_in.as_posix(),
    }
    result = subprocess.run(
        [bash(), *GITHUB_BASH, "-c", WITH_STAND_IN, script.as_posix()],
        cwd=REPO_ROOT / step["working-directory"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


ADMITTED = (0, "releases admit: v1.3.0: admitted|tag=v1.3.0")


def test_eko115_k04_readmission_step_passes_an_admitted_run(tmp_path: Path) -> None:
    code, log = run_readmission(tmp_path, ADMITTED, 0)
    assert code == 0, log


@pytest.mark.parametrize(
    ("admit", "tag_commit"),
    [
        ((1, "releases admit: v1.3.0: lower than the published release v1.3.1"), 0),
        ((1, "releases admit: v1.3.0: already published; a published release never changes"), 0),
        ((1, "releases admit: v1.3.0: started by an account that may not publish"), 0),
        ((2, "releases admit: the check itself failed: x"), 0),
        ((0, "releases admit: v1.3.1: admitted|tag=v1.3.1"), 0),
        (ADMITTED, 1),
        (ADMITTED, 2),
    ],
    ids=[
        "lower",
        "published",
        "another-rerunner",
        "cannot-tell",
        "another-tag",
        "tag-moved",
        "tag-cannot-tell",
    ],
)
def test_eko115_k04_readmission_step_stops_a_refused_run(
    tmp_path: Path, admit: tuple[int, str], tag_commit: int
) -> None:
    code, log = run_readmission(tmp_path, admit, tag_commit)
    assert code != 0, log


# `releases tag-commit`: the tag still names the run's commit ---------------------------------


class Api:
    """A stand-in GitHub REST API: refs and tag objects by path."""

    def __init__(self, answers: dict[str, tuple[int, Any]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> Response:
        path = url.removeprefix("https://api.github.com")
        self.calls.append((path, headers))
        status, payload = self.answers.get(path, (404, {"message": "Not Found"}))
        return Response(status, {}, json.dumps(payload).encode())


REF = "/repos/TanerCRB/Eko_CRM/git/ref/tags/v1.3.0"


def tags(api: Api, token: str) -> GitHubTags:
    return GitHubTags(token, "TanerCRB/Eko_CRM", api)


def test_eko115_k04_tag_commit_of_a_lightweight_tag() -> None:
    api = Api({REF: (200, {"object": {"type": "commit", "sha": SHA}})})
    assert tags(api, "t").commit_of("v1.3.0") == SHA
    assert api.calls[0][1]["Authorization"] == "Bearer t"


def test_eko115_k04_tag_commit_of_an_annotated_tag() -> None:
    api = Api(
        {
            REF: (200, {"object": {"type": "tag", "sha": TAG_OBJECT}}),
            f"/repos/TanerCRB/Eko_CRM/git/tags/{TAG_OBJECT}": (
                200,
                {"object": {"type": "commit", "sha": OTHER}},
            ),
        }
    )
    assert tags(api, "t").commit_of("v1.3.0") == OTHER


def test_eko115_k04_tag_commit_of_a_deleted_tag_is_none() -> None:
    assert tags(Api({}), "t").commit_of("v1.3.0") is None


@pytest.mark.parametrize(
    "answer",
    [(401, {}), (500, {}), (200, [{"object": {}}]), (200, {"object": {"type": "tree"}})],
    ids=["refused", "error", "a-list", "not-a-commit"],
)
def test_eko115_k04_tag_commit_cannot_tell(answer: tuple[int, Any]) -> None:
    with pytest.raises(CannotTell):
        tags(Api({REF: answer}), "t").commit_of("v1.3.0")


def test_eko115_k04_tag_commit_without_a_token_cannot_tell() -> None:
    with pytest.raises(CannotTell):
        tags(Api({}), "").commit_of("v1.3.0")


def _cli(monkeypatch: pytest.MonkeyPatch, api: Api, commit: str) -> tuple[int, str]:
    monkeypatch.setenv("RELEASE_REPO_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "TanerCRB/Eko_CRM")
    out = io.StringIO()
    argv = ["tag-commit", "--tag", "v1.3.0", "--commit", commit]
    return releases.main(argv, out, tags=GitHubTags("t", "TanerCRB/Eko_CRM", api)), out.getvalue()


def test_eko115_k04_tag_commit_cli_passes_when_the_tag_names_the_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Api({REF: (200, {"object": {"type": "commit", "sha": SHA}})})
    code, output = _cli(monkeypatch, api, SHA)
    assert code == 0, output


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({REF: (200, {"object": {"type": "commit", "sha": OTHER}})}, 1),
        ({}, 1),
        ({REF: (403, {})}, 2),
    ],
    ids=["moved", "deleted", "cannot-tell"],
)
def test_eko115_k04_contrast_tag_commit_cli_refuses_a_moved_or_deleted_tag(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, tuple[int, Any]], expected: int
) -> None:
    code, output = _cli(monkeypatch, Api(answers), SHA)
    assert code == expected, output
