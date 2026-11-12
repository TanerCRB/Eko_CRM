"""EKO-1-15 K-04 (ADR-0004-C30): nothing but an admitted release run writes to the registry.

(a) Across every workflow file only the release path holds `packages: write`, behind the
admission; (b) the admission decision on fixture events; (c) registry login uses `GITHUB_TOKEN`
only. The admission reads a stand-in record and a stand-in reachability (tests/static/
release_doubles.py).
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.static.release_doubles import BRANCH, MAIN, MAIN_OLDER, ReachDouble, record
from tests.support import release_workflow as rw
from tests.support.releases import CannotTell, Event, admission
from tests.support.repo import REPO_ROOT

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
Workflow = dict[Any, Any]


def tag_push(tag: str, sha: str = MAIN, actor: str = "TanerCRB", **changes: str) -> Event:
    fields = {
        "name": "push",
        "ref": f"refs/tags/{tag}",
        "sha": sha,
        "actor": actor,
        "triggering_actor": actor,
        **changes,
    }
    return Event(**fields)


ADMITTED = tag_push("v1.3.0")

# Each refusal differs from ADMITTED in one element; the record holds v1.2.0 on main.
REFUSALS: dict[str, Event] = {
    "pull-request": tag_push("v1.3.0", name="pull_request", ref="refs/pull/7/merge"),
    "push-to-main": tag_push("v1.3.0", ref="refs/heads/main"),
    "tag-outside-the-form": tag_push("release-1.3.0"),
    "lower-than-published": tag_push("v1.1.9"),
    "commit-not-on-main": tag_push("v1.3.0", sha=BRANCH),
    "another-account": tag_push("v1.3.0", actor="someone-else"),
}


def published() -> Any:
    return record("v1.2.0")


def test_eko115_k04_admitted_release_run() -> None:
    decision = admission(ADMITTED, published(), ReachDouble())
    assert decision.admitted, decision.reason
    assert decision.tag == "v1.3.0"


@pytest.mark.parametrize("case_id", sorted(REFUSALS))
def test_eko115_k04_refused_event(case_id: str) -> None:
    decision = admission(REFUSALS[case_id], published(), ReachDouble())
    assert not decision.admitted, case_id
    assert decision.reason


@pytest.mark.parametrize(
    "tag",
    ["v1.2.0-rc1", "v1.02.0", "v1.2", "1.3.0", "v1.3.0.0", "V1.3.0", "v01.3.0", "v1.3.0+b1", "v"],
)
def test_eko115_k04_edge_tag_outside_the_form_is_refused(tag: str) -> None:
    decision = admission(tag_push(tag), record(), ReachDouble())
    assert not decision.admitted, tag


def test_eko115_k04_edge_numeric_not_text_order() -> None:
    assert admission(tag_push("v1.10.0"), record("v1.9.0"), ReachDouble()).admitted
    assert not admission(tag_push("v1.9.0"), record("v1.10.0"), ReachDouble()).admitted


def test_eko115_k04_edge_first_release_is_admitted() -> None:
    assert admission(tag_push("v0.1.0"), record(), ReachDouble()).admitted


def test_eko115_k04_edge_commit_on_main_but_not_its_head_is_admitted() -> None:
    assert admission(tag_push("v1.3.0", sha=MAIN_OLDER), published(), ReachDouble()).admitted


def test_eko115_k04_edge_rerun_by_another_account_is_refused() -> None:
    event = tag_push("v1.3.0", triggering_actor="someone-else")
    assert not admission(event, published(), ReachDouble()).admitted


def test_eko115_k04_edge_reachability_unknown_is_not_an_admission() -> None:
    reach = ReachDouble(unknown={MAIN})
    with pytest.raises(CannotTell):
        admission(ADMITTED, published(), reach)


def test_eko115_k04_edge_lower_than_an_unreachable_release_is_admitted() -> None:
    # A branch tag's record entry is not a release to any reader (G-6 A+), the admission included.
    assert admission(ADMITTED, record("v2.0.0", commit=BRANCH), ReachDouble()).admitted


# (a) packages: write across every workflow file ----------------------------------------------


def workflows() -> dict[str, Workflow]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOWS.glob("*.y*ml"))
    }


def test_eko115_k04_only_the_release_path_holds_packages_write() -> None:
    flows = workflows()
    assert "release.yml" in flows
    assert rw.registry_write_violations(flows) == []


def test_eko115_k04_release_workflow_runs_only_on_tags() -> None:
    assert rw.release_trigger_violations(workflows()["release.yml"]) == []


def test_eko115_k04_registry_login_uses_only_the_run_token() -> None:
    assert rw.registry_login_violations(workflows()) == []


def _job(flow: Workflow, name: str, key: str, value: Any) -> Workflow:
    changed = copy.deepcopy(flow)
    changed["jobs"][name][key] = value
    return changed


def _drop_permissions(flow: Workflow, name: str) -> Workflow:
    changed = copy.deepcopy(flow)
    changed["jobs"][name].pop("permissions", None)
    changed.pop("permissions", None)
    return changed


Change = Callable[[dict[str, Workflow]], dict[str, Workflow]]


def _in(file: str, change: Callable[[Workflow], Workflow]) -> Change:
    return lambda flows: {**flows, file: change(flows[file])}


WRITE_PLANTS: dict[str, Change] = {
    "ci-workflow-level": _in(
        "ci.yml",
        lambda f: {**f, "permissions": {"contents": "read", "packages": "write"}},
    ),
    "ci-job-level": _in(
        "ci.yml", lambda f: _job(f, "backend", "permissions", {"packages": "write"})
    ),
    "ci-write-all": _in("ci.yml", lambda f: {**f, "permissions": "write-all"}),
    "ci-no-permissions-anywhere": _in("ci.yml", lambda f: _drop_permissions(f, "backend")),
    "release-check-job-writes": _in(
        "release.yml",
        lambda f: _job(f, "backend", "permissions", {"contents": "read", "packages": "write"}),
    ),
    "release-publish-without-admission": _in(
        "release.yml", lambda f: _job(f, "publish", "if", "success()")
    ),
    "release-publish-not-needing-admission": _in(
        "release.yml",
        lambda f: _job(
            f, "publish", "needs", [n for n in f["jobs"]["publish"]["needs"] if n != "admission"]
        ),
    ),
}


@pytest.mark.parametrize("case_id", sorted(WRITE_PLANTS))
def test_eko115_k04_registry_write_check_fails_on_a_plant(case_id: str) -> None:
    flows = workflows()
    assert rw.registry_write_violations(flows) == []
    assert rw.registry_write_violations(WRITE_PLANTS[case_id](flows)) != [], case_id


def test_eko115_k04_packages_read_is_allowed_beside_contents_read() -> None:
    flows = workflows()
    planted = _in(
        "ci.yml",
        lambda f: _job(f, "backend", "permissions", {"contents": "read", "packages": "read"}),
    )(flows)
    assert rw.registry_write_violations(planted) == []


@pytest.mark.parametrize("pattern", ["*", "**", "v*-*"])
def test_eko115_k04_trigger_check_fails_on_a_widened_or_other_trigger(pattern: str) -> None:
    flow = copy.deepcopy(workflows()["release.yml"])
    flow[True] = {"push": {"tags": [pattern]}, "pull_request": None}
    assert rw.release_trigger_violations(flow) != []


def test_eko115_k04_login_check_fails_on_a_stored_secret() -> None:
    flows = workflows()
    flow = copy.deepcopy(flows["release.yml"])
    for step in flow["jobs"]["publish"]["steps"]:
        if "docker login" in str(step.get("run", "")):
            step["env"] = {**(step.get("env") or {}), "TOKEN": "${{ secrets.GHCR_PAT }}"}
    assert rw.registry_login_violations({**flows, "release.yml": flow}) != []


# A-05: the admission command's exit code is the run's outcome ---------------------------------


def _admit(monkeypatch: pytest.MonkeyPatch, event: Event, rec: Any, reach: Any) -> tuple[int, str]:
    import io

    from tests.support import releases

    for name, value in {
        "GITHUB_EVENT_NAME": event.name,
        "GITHUB_REF": event.ref,
        "GITHUB_SHA": event.sha,
        "GITHUB_ACTOR": event.actor,
        "GITHUB_TRIGGERING_ACTOR": event.triggering_actor,
    }.items():
        monkeypatch.setenv(name, value)
    out = io.StringIO()
    code = releases.main(["admit"], out, record=rec, reach=reach)
    return code, out.getvalue()


def test_eko115_k04_a05_admit_exits_0_and_names_the_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _admit(monkeypatch, ADMITTED, published(), ReachDouble())
    assert code == 0 and "tag=v1.3.0" in output.splitlines(), output


@pytest.mark.parametrize("case_id", sorted(REFUSALS))
def test_eko115_k04_a05_admit_exits_1_on_a_refusal(
    monkeypatch: pytest.MonkeyPatch, case_id: str
) -> None:
    code, output = _admit(monkeypatch, REFUSALS[case_id], published(), ReachDouble())
    assert code == 1 and "tag=" not in output, output


def test_eko115_k04_a05_admit_exits_2_when_it_cannot_tell(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.static.release_doubles import RecordDouble

    refused = RecordDouble(releases=published().releases, refuse_listing=True)
    code, output = _admit(monkeypatch, ADMITTED, refused, ReachDouble())
    assert code == 2 and "tag=" not in output, output
    code, output = _admit(monkeypatch, ADMITTED, published(), ReachDouble(unknown={MAIN}))
    assert code == 2 and "tag=" not in output, output
