"""EKO-1-15 K-07, static half, on both bases (QA F-1): the check on `ci.yml` holds while this
change is the change set and still holds once it is on the base, and catches an unlisted change
against either.

Neither base is read from the live branch (`CHANGESET_BASE`): the pre-merge base is the `ci.yml`
of 14e9576 (the base this change was built on), kept as a fixture; the merged base is the head's
own `ci.yml`, which is what the base holds once this change is merged.

Where a check holds the pre-merge base against the head it is the claim about this change, judged
on its own head (EKO_1_15_HEAD, `claim_head`), not on the live worktree (EKO-1-23, #110).
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.test_eko115_k07_unchanged import CI, EKO_1_15_HEAD, FAILING, _job
from tests.static.test_k07_changeset import in_worktree
from tests.support import release_workflow as rw
from tests.support.fixed_pair import file_at

Workflow = dict[Any, Any]
PRE_MERGE = Path(__file__).parent / "fixtures" / "ci_before_eko115.yml"


def head() -> Workflow:
    text = in_worktree(".github/workflows/ci.yml")
    assert text is not None
    flow: Workflow = yaml.safe_load(text)
    return flow


def base(which: str) -> Workflow:
    if which == "merged":
        return head()
    flow: Workflow = yaml.safe_load(PRE_MERGE.read_text(encoding="utf-8"))
    return flow


def claim_head(which: str) -> Workflow:
    """EKO-1-15's own head against the pre-merge base; the live head against the merged one."""
    if which == "merged":
        return head()
    text = file_at(EKO_1_15_HEAD, CI)
    assert text is not None
    flow: Workflow = yaml.safe_load(text)
    return flow


BASES = ("pre-merge", "merged")


def test_eko115_k07_pre_merge_fixture_is_the_base_before_this_change() -> None:
    before = base("pre-merge")
    assert rw.CI_LOGIN_STEP not in before["jobs"]["backend"]["steps"]
    assert "permissions" not in before["jobs"]["runtime"]


@pytest.mark.parametrize("which", BASES)
def test_eko115_k07_ci_unchanged_holds_on_both_bases(which: str) -> None:
    assert rw.ci_unchanged_violations(base(which), claim_head(which)) == []


@pytest.mark.parametrize("which", BASES)
@pytest.mark.parametrize("case_id", sorted(FAILING))
def test_eko115_k07_ci_check_fails_on_a_plant_on_both_bases(which: str, case_id: str) -> None:
    assert rw.ci_unchanged_violations(base(which), FAILING[case_id](head())) != [], case_id


@pytest.mark.parametrize("which", BASES)
def test_eko115_k07_contrast_packages_read_on_a_record_job_on_both_bases(which: str) -> None:
    planted = _job("backend", "permissions", {"contents": "read", "packages": "read"})(
        claim_head(which)
    )
    assert rw.ci_unchanged_violations(base(which), planted) == []


@pytest.mark.parametrize("which", BASES)
def test_eko115_k07_an_unlisted_step_in_a_record_job_fails_on_both_bases(which: str) -> None:
    changed = head()
    changed["jobs"]["backend"]["steps"].insert(1, {"name": "planted", "run": "true"})
    assert rw.ci_unchanged_violations(base(which), changed) != []
