"""EKO-1-23 (#110): EKO-1-13's change-set claims are judged on EKO-1-13's own change set (PR #81:
base 1bfaa5a, head 947ff40), not on the live branch.

The claims: `create_app()`'s route table and OpenAPI document equal the base's, and the EKO-1-11
refusal, EKO-1-14 backup and C28 test files are unchanged. What stays live, judged on the live head
alone: the health body is status-only, no fixture route ships, the route read is not empty.

Every plant lives in a throwaway repository (tests/support/fixed_pair.py) or in a temporary copy
of the application; the real repository is never written. A planted route is a variant of
`create_app()`, never a self-wired app (ADR-0005, fixture rule).
"""

import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.static import test_adr0005_eko113_changeset as claim
from tests.support.fixed_pair import (
    ABSENT,
    Throwaway,
    add,
    chmod,
    delete,
    edit,
    modify,
    rename,
)
from tests.support.repo import REPO_ROOT, git

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# PR #81's merge, recorded independently of the check's own constants.
EKO_1_13_MERGE = "cc73e138c01ec2ff1f44a4e40698ae63e3ab0ae3"
PAIR_BASE = "1bfaa5aa57cb854739d230e24b42655d66d1270f"
PAIR_HEAD = "947ff40efac06b13d6df48b6650024503f2e7308"
PR_146057A = "146057a88b2ed2db658261690a5b420f7dfa2f8d"

MAIN = "backend/app/main.py"
HEALTH = "backend/app/api/health.py"
INCLUDE = '        app.include_router(health_router, prefix="/api")\n'
HEALTH_FIELD = '    status: Literal["ok", "unavailable"]\n'
APP = ("backend/app", "backend/migrations")
TESTS = "backend/tests/runtime/"
BACKUP_FAILURE = f"{TESTS}test_adr0004_backup_failure_line.py"
C15 = f"{TESTS}test_adr0004_c15_backup_set_contents.py"

Surface = dict[str, Any]
Surfaces = tuple[Surface, Surface]

# (where the live plant sits, $CHANGESET_BASE): every placement and every base appears.
LIVE_STATES = {
    "committed-base-unset": ("committed", None),
    "committed-base-empty": ("committed", ""),
    "worktree-base-pair-base": ("worktree", PAIR_BASE),
    "worktree-base-pair-head": ("worktree", PAIR_HEAD),
    "committed-base-pr-146057a": ("committed", PR_146057A),
    "worktree-base-missing-commit": ("worktree", ABSENT),
}


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    monkeypatch.delenv("CHANGESET_BASE", raising=False)
    return Throwaway(tmp_path / "repo", PAIR_HEAD, monkeypatch)


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> Surfaces:
    return claim.pair_surfaces(tmp_path_factory.mktemp("pair"))


@pytest.fixture(scope="module")
def placed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Throwaway, Surface]]:
    """The live tree with a new endpoint, committed and in the working tree (built once)."""
    built = {}
    for placement in ("committed", "worktree"):
        repo = Throwaway(tmp_path_factory.mktemp(placement) / "repo", PAIR_HEAD)
        new = route_line("/api/planted")
        if placement == "committed":
            repo.checkout_files(repo.commit(PAIR_HEAD, edit(MAIN, INCLUDE, new)), *APP)
        else:
            repo.checkout_files(PAIR_HEAD, *APP)
            rewrite(repo, MAIN, INCLUDE, new)
        env = repo._env()
        text = subprocess.run(
            [sys.executable, "-c", claim.SURFACE],
            cwd=repo.work / "backend",
            env={k: v for k, v in env.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        built[placement] = (repo, json.loads(text))
    return built


def route_line(path: str) -> str:
    return f'{INCLUDE}        app.add_api_route("{path}", lambda: {{}}, methods=["GET"])\n'


def rewrite(throwaway: Throwaway, path: str, old: str, new: str) -> None:
    """The same edit in the throwaway's working tree, whatever line endings the checkout wrote."""
    file = throwaway.work / path
    text = file.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert old in text, (path, old)
    file.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def live_surface(throwaway: Throwaway, placement: str, path: str, old: str, new: str) -> Surface:
    """`create_app()` of the live tree: PAIR_HEAD plus one edit, committed or in the worktree."""
    if placement == "committed":
        throwaway.checkout_files(throwaway.commit(PAIR_HEAD, edit(path, old, new)), *APP)
    else:
        throwaway.checkout_files(PAIR_HEAD, *APP)
        rewrite(throwaway, path, old, new)
    return claim.surface(throwaway.work / "backend")


# K-02, claim 1: a live route the pair does not have -----------------------------------------


@pytest.mark.parametrize("state", sorted(LIVE_STATES))
def test_eko123_eko113_surface_claim_ignores_a_live_change_set_with_a_new_endpoint(
    state: str,
    pair: Surfaces,
    placed: dict[str, tuple[Throwaway, Surface]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    placement, base = LIVE_STATES[state]
    repo, live = placed[placement]
    repo.select(monkeypatch)
    monkeypatch.delenv("CHANGESET_BASE", raising=False)
    if base is not None:
        monkeypatch.setenv("CHANGESET_BASE", base)
    assert "GET /api/planted" in live["routes"], "precondition: the live route table has the plant"
    assert claim.surface_problems(pair[0], live) != [], "precondition: the old reading was red"
    claim.test_adr0005_eko113_changeset_route_table_openapi_and_health_body(pair, live)


# K-03, claim 1 ------------------------------------------------------------------------------

SURFACE_PLANTS = {
    "route-added": (edit(MAIN, INCLUDE, route_line("/api/planted")), "routes"),
    "route-removed": (edit(MAIN, INCLUDE, ""), "routes"),
    "openapi-only": (edit(MAIN, 'title="Eko_CRM API"', 'title="Eko_CRM API planted"'), "openapi"),
}


@pytest.mark.parametrize("case", sorted(SURFACE_PLANTS))
def test_eko123_eko113_surface_claim_fails_on_one_change_inside_the_pair(
    case: str, pair: Surfaces, throwaway: Throwaway, tmp_path: Path
) -> None:
    change, key = SURFACE_PLANTS[case]
    planted = claim.surface_at(throwaway.commit(PAIR_HEAD, change), tmp_path / "planted")
    assert claim.surface_problems(*pair) == [], "the same pair without the plant is clean"
    problems = claim.surface_problems(pair[0], planted)
    assert f"{key} differs from the base branch's" in problems
    if key == "openapi":
        assert "routes differs from the base branch's" not in problems
    with pytest.raises(AssertionError, match=f"{key} differs"):
        claim.test_adr0005_eko113_changeset_route_table_openapi_and_health_body(
            (pair[0], planted), pair[1]
        )


def test_eko123_eko113_surface_claim_contrast_the_unplanted_pair_passes(pair: Surfaces) -> None:
    assert pair[0]["routes"] and pair[0]["routes"] == pair[1]["routes"]
    assert claim.surface_problems(*pair) == []
    claim.test_adr0005_eko113_changeset_route_table_openapi_and_health_body(pair, pair[1])


# K-05: the rules on the live head alone stay judged on the live head ------------------------

HEAD_ONLY_PLANTS = {
    "fixture-route": (MAIN, INCLUDE, route_line("/api/fixture/boom"), "fixture route"),
    "fixture-in-a-longer-segment": (
        MAIN,
        INCLUDE,
        route_line("/api/prefixfixturesuffix"),
        "fixture route",
    ),
    "health-second-field": (
        HEALTH,
        HEALTH_FIELD,
        f'{HEALTH_FIELD}    revision: str = "x"\n',
        "health body",
    ),
}


@pytest.mark.parametrize("case", sorted(HEAD_ONLY_PLANTS))
def test_eko123_eko113_live_head_rules_still_fail_on_a_live_plant(
    case: str, pair: Surfaces, throwaway: Throwaway
) -> None:
    path, old, new, named = HEAD_ONLY_PLANTS[case]
    live = live_surface(throwaway, "committed", path, old, new)
    assert claim.surface_problems(live, live) != [], "precondition: the live head breaks the rule"
    with pytest.raises(AssertionError, match=named):
        claim.test_adr0005_eko113_changeset_route_table_openapi_and_health_body(pair, live)


def test_eko123_eko113_live_head_with_an_empty_route_read_still_fails(pair: Surfaces) -> None:
    empty = {**pair[1], "routes": []}
    with pytest.raises(AssertionError, match="no live route read"):
        claim.test_adr0005_eko113_changeset_route_table_openapi_and_health_body(pair, empty)


# K-02, claim 2: a live edit of a protected test ---------------------------------------------


def plant_protected(repo: Throwaway) -> None:
    modify(BACKUP_FAILURE)(repo)
    modify(C15)(repo)


@pytest.fixture(scope="module")
def protected_placed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Throwaway]:
    built = {}
    for placement in ("committed", "worktree"):
        repo = Throwaway(tmp_path_factory.mktemp(placement) / "repo", PAIR_HEAD)
        if placement == "committed":
            repo.checkout_files(repo.commit(PAIR_HEAD, plant_protected), BACKUP_FAILURE, C15)
        else:
            repo.checkout_files(PAIR_HEAD, BACKUP_FAILURE, C15)
            (repo.work / BACKUP_FAILURE).write_text("planted\n", encoding="utf-8")
            (repo.work / C15).write_text("planted\n", encoding="utf-8")
            (repo.work / TESTS / "test_adr0004_c13_untracked.py").write_text(
                "x\n", encoding="utf-8"
            )
        built[placement] = repo
    return built


@pytest.mark.parametrize("state", sorted(LIVE_STATES))
def test_eko123_eko113_protected_claim_ignores_a_live_edit_of_a_protected_test(
    state: str, protected_placed: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch
) -> None:
    placement, base = LIVE_STATES[state]
    protected_placed[placement].select(monkeypatch)
    monkeypatch.delenv("CHANGESET_BASE", raising=False)
    if base is not None:
        monkeypatch.setenv("CHANGESET_BASE", base)
    live = set(git("diff", "--name-only", PAIR_HEAD, "--", TESTS).split())
    live |= set(git("ls-files", "--others", "--exclude-standard").split())
    assert {BACKUP_FAILURE, C15} <= live, "precondition: the live change set holds the plants"
    old_reading = claim.protected_problems(sorted(live), {C15: ["planted"]})
    assert old_reading != [], "precondition: the old reading was red"
    claim.test_adr0005_eko113_changeset_refusal_backup_and_c28_tests_unchanged()


# K-03, claim 2 ------------------------------------------------------------------------------

REVISION_CHECK = f"{TESTS}test_adr0004_c13_backend_revision_check.py"
WORKER_CHECK = f"{TESTS}test_adr0006_c13_worker_revision_check.py"
C28 = f"{TESTS}test_k04_c28_failed_first_init.py"
PROTECTED_PLANTS = {
    "added": (add(f"{TESTS}test_adr0004_c13_planted.py"), f"{TESTS}test_adr0004_c13_planted.py"),
    "modified": (modify(BACKUP_FAILURE), BACKUP_FAILURE),
    "deleted": (delete(WORKER_CHECK), WORKER_CHECK),
    "renamed": (
        rename(REVISION_CHECK, f"{TESTS}test_adr0004_c13_renamed.py"),
        f"{TESTS}test_adr0004_c13_renamed.py",
    ),
    "mode-only": (chmod(C28), C28),
    "line-outside-the-allowed-edit": (modify(C15), C15),
}
PASSING_PLANTS = {
    "line-inside-the-allowed-edit": edit(
        C15,
        "first_run = statement_logged_run(backup_lab)",
        "first_run = statement_logged_run(backup_lab)  # twin",
    ),
    "prefix-twin": add(f"{TESTS}test_adr0004_c130_x.py"),
}


@pytest.mark.parametrize("case", sorted(PROTECTED_PLANTS))
def test_eko123_eko113_protected_claim_fails_on_one_change_inside_the_pair(
    case: str, throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    change, path = PROTECTED_PLANTS[case]
    head = throwaway.commit(PAIR_HEAD, change)
    assert claim.eko_1_13_protected_problems() == [], "the same pair without the plant is clean"
    problems = claim.eko_1_13_protected_problems(head=head)
    assert [p for p in problems if p.startswith(f"{path}:")] != [], problems
    # The original test, with only the pair's head replaced by the planted head.
    monkeypatch.setattr(claim.eko_1_13_protected_problems, "__defaults__", (PAIR_BASE, head))
    with pytest.raises(AssertionError, match=path):
        claim.test_adr0005_eko113_changeset_refusal_backup_and_c28_tests_unchanged()


@pytest.mark.parametrize("case", sorted(PASSING_PLANTS))
def test_eko123_eko113_protected_claim_contrast_a_twin_of_a_protected_change_passes(
    case: str, throwaway: Throwaway
) -> None:
    head = throwaway.commit(PAIR_HEAD, PASSING_PLANTS[case])
    assert git("diff", "--name-only", PAIR_HEAD, head).strip() != "", "precondition: a change"
    assert claim.eko_1_13_protected_problems(head=head) == []


def test_eko123_eko113_protected_claim_contrast_the_unplanted_pair_passes() -> None:
    assert claim.eko_1_13_protected_problems() == []


# K-04 ---------------------------------------------------------------------------------------


def test_eko123_eko113_claims_read_the_parents_of_pr_81s_merge() -> None:
    assert git("log", "-1", "--format=%s", EKO_1_13_MERGE).startswith("Merge pull request #81 ")
    parents = git("rev-parse", f"{EKO_1_13_MERGE}^1", f"{EKO_1_13_MERGE}^2").split()
    assert parents == [PAIR_BASE, PAIR_HEAD]
    assert parents[0] != parents[1]
    assert git("merge-base", *parents).strip() == parents[0]
    for check in (claim.pair_surfaces, claim.eko_1_13_protected_problems):
        defaults = inspect.signature(check).parameters
        assert [defaults["base"].default, defaults["head"].default] == parents


def commit_is_absent() -> bool:
    found = subprocess.run(
        ["git", "cat-file", "-e", f"{ABSENT}^{{commit}}"], cwd=REPO_ROOT, capture_output=True
    )
    return found.returncode != 0


@pytest.mark.parametrize("side", ["base", "head"])
def test_eko123_eko113_surface_claim_errors_on_an_unavailable_commit(
    side: str, tmp_path: Path
) -> None:
    assert commit_is_absent(), "precondition: the commit is not in the object store"
    with pytest.raises(subprocess.CalledProcessError):
        claim.pair_surfaces(tmp_path, **{side: ABSENT})


@pytest.mark.parametrize("side", ["base", "head"])
def test_eko123_eko113_protected_claim_errors_on_an_unavailable_commit(side: str) -> None:
    assert commit_is_absent(), "precondition: the commit is not in the object store"
    with pytest.raises(subprocess.CalledProcessError):
        claim.eko_1_13_protected_problems(**{side: ABSENT})
