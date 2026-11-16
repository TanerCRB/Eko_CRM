"""EKO-1-23 QA (K-02): the EKO-1-19 claims ignore `$CHANGESET_BASE` even when it names a real commit
from which the claim would be red.

`test_eko123_workflow_claims.py` sets `CHANGESET_BASE` to unset, empty, the pair's base, the pair's
head, 146057a and a missing commit. A claim that took its base from `$CHANGESET_BASE` stays green
on the first five (the claim happens to hold from each of them), so only the missing commit caught
it, and by a git error rather than by the claim's own assertion. Here the variable names EKO-1-13's
base (1bfaa5a), older than EKO-1-19's pair: the text-level job check and the release check are red
from it, so a claim that read it would fail on its own assertion.
"""

import subprocess
from collections.abc import Callable

import pytest

from tests.static import test_eko119_k03_release_mode_ci as m119
from tests.support.fixed_pair import file_at
from tests.support.repo import REPO_ROOT

CI = ".github/workflows/ci.yml"
RELEASE = ".github/workflows/release.yml"
OLDER = "1bfaa5aa57cb854739d230e24b42655d66d1270f"
EKO_1_19_HEAD = "726befdd86cebbd67d1796f5cc79f4f7121685d3"


def jobs_red_from_older() -> bool:
    base, head = file_at(OLDER, CI), file_at(EKO_1_19_HEAD, CI)
    assert base is not None and head is not None
    try:
        m119.assert_existing_jobs_unchanged(base, head)
    except AssertionError:
        return True
    return False


def release_red_from_older() -> bool:
    return file_at(OLDER, RELEASE) != file_at(EKO_1_19_HEAD, RELEASE)


CLAIMS: dict[str, tuple[Callable[[], bool], Callable[[], None]]] = {
    "eko119-jobs": (
        jobs_red_from_older,
        m119.test_eko119_k03_every_existing_ci_job_is_byte_identical,
    ),
    "eko119-release": (release_red_from_older, m119.test_eko119_k06_release_workflow_unchanged),
}


@pytest.mark.parametrize("claim", sorted(CLAIMS))
def test_eko123_qa_eko119_claims_ignore_a_changeset_base_they_would_fail_from(
    claim: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    red_from_older, body = CLAIMS[claim]
    assert (
        subprocess.run(
            ["git", "cat-file", "-e", f"{OLDER}^{{commit}}"], cwd=REPO_ROOT, capture_output=True
        ).returncode
        == 0
    ), "precondition: the older commit is in the object store"
    assert red_from_older(), "precondition: judged from the older commit, the claim is red"
    monkeypatch.setenv("CHANGESET_BASE", OLDER)
    body()
