"""EKO-1-15 K-07, QA (re-verification of F-1): the symmetric revert undoes the allowed differences
on both sides, so a change *inside* an allowed step (its env, its `with`, the login step's
token) must still be red against either base; and the allowed difference itself, changed in the
same element by one value, is the contrast.

Bases as in test_eko115_k07_unchanged_on_both_bases.py: the pre-merge fixture and the head's own
`ci.yml` (the base once this change is merged). Neither reads the live `CHANGESET_BASE`.
"""

import copy
from typing import Any

import pytest

from tests.static.test_eko115_k07_unchanged_on_both_bases import BASES, base, claim_head, head
from tests.support import release_workflow as rw

Workflow = dict[Any, Any]


def _step(flow: Workflow, job: str, needle: str) -> dict[str, Any]:
    found = [s for s in flow["jobs"][job]["steps"] if needle in str(s.get("run", ""))]
    assert len(found) == 1, (job, needle)
    step: dict[str, Any] = found[0]
    return step


def _env_added(job: str, needle: str) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        step = _step(changed, job, needle)
        step["env"] = {**(step.get("env") or {}), "RELEASE_MAIN_REF": "HEAD"}
        return changed

    return apply


def _login_token(job: str, token: str) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        step = _step(changed, job, "docker login")
        step["env"] = {**step["env"], "TOKEN": token}
        return changed

    return apply


def _full_history_with(job: str, extra: dict[str, Any]) -> Any:
    def apply(flow: Workflow) -> Workflow:
        changed = copy.deepcopy(flow)
        step = changed["jobs"][job]["steps"][0]
        assert str(step.get("uses", "")).startswith("actions/checkout@")
        step["with"] = {**step["with"], **extra}
        return changed

    return apply


INSIDE = {
    "env-key-in-the-compat-step": _env_added("backend", "openapi_compat"),
    "env-key-in-the-runtime-tests-step": _env_added("runtime", "pytest"),
    "login-token-from-a-stored-secret-backend": _login_token("backend", "${{ secrets.GHCR_PAT }}"),
    "login-token-from-a-stored-secret-runtime": _login_token("runtime", "${{ secrets.GHCR_PAT }}"),
    "checkout-ref-added-on-the-full-history-checkout": _full_history_with("runtime", {"ref": "x"}),
}


@pytest.mark.parametrize("which", BASES)
@pytest.mark.parametrize("case_id", sorted(INSIDE))
def test_eko115_k07_qa_a_change_inside_an_allowed_step_fails_on_both_bases(
    which: str, case_id: str
) -> None:
    assert rw.ci_unchanged_violations(base(which), INSIDE[case_id](head())) != [], case_id


@pytest.mark.parametrize("which", BASES)
def test_eko115_k07_qa_contrast_the_login_token_as_allowed_passes_on_both_bases(which: str) -> None:
    same = _login_token("backend", "${{ github.token }}")(claim_head(which))
    assert rw.ci_unchanged_violations(base(which), same) == []
