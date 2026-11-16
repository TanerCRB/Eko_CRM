"""EKO-1-23 (#110): the `ci.yml` and `release.yml` claims of EKO-1-15 (PR #85), EKO-1-19 (PR #96)
and EKO-1-20 (PR #113) are judged on each task's own change set (the parents of its PR merge
commit), not on the live branch.

A later branch that changes a job, a step, a permission or one line of `release.yml` leaves the
claims green; a one-change plant inside the original pair, or a pair commit that is not in the
object store, turns them red. What every branch must meet ("builds once", C31) stays judged on the
live `release.yml`. Plants live in a throwaway repository (tests/support/fixed_pair.py); the real
repository is never written.
"""

import inspect
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.static import test_eko115_k07_qa_inside_allowed_steps_on_both_bases as q115
from tests.static import test_eko115_k07_unchanged as m115
from tests.static import test_eko115_k07_unchanged_on_both_bases as b115
from tests.static import test_eko119_k03_release_mode_ci as m119
from tests.static import test_eko120_ci_timeout_retune as m120
from tests.static import test_k07_changeset as k07
from tests.support.fixed_pair import ABSENT, Throwaway, edit, file_at
from tests.support.repo import REPO_ROOT, git

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

CI = ".github/workflows/ci.yml"
RELEASE = ".github/workflows/release.yml"
PR_146057A = "146057a88b2ed2db658261690a5b420f7dfa2f8d"
# Each PR's merge commit and its parents, recorded independently of the checks' own constants.
EKO_1_15 = (
    "0e525b6edb584ca0589cd7d64ae572f8aa9a582c",
    "14e9576a1bbf17e94f3a281e2061b0c4ad4a6563",
    "0d221229917c0fea3d7b99efaa3cce578e51087f",
)
EKO_1_19 = (
    "794c04abb0c92292c506861e819ea0919b8d5fb6",
    "e895ce17ad46b8f50df6b92b2dc11ed9af8af110",
    "726befdd86cebbd67d1796f5cc79f4f7121685d3",
)
EKO_1_20 = (
    "5f1b1a08a44c435a1012ea7552da406e4a40ecfc",
    "32deb05d257610f80a45b890fec84d7d153d2f31",
    "b21e45aa80b8517ea20be09c87d5690069b92ae9",
)

LOCK_RUN = "        run: uv lock --locked\n"
STEP_CHANGED = edit(CI, LOCK_RUN, "        run: uv lock --locked --offline\n")
PERMISSION_CHANGED = edit(CI, "      packages: read\n", "      packages: write\n")
RETUNED = edit(CI, "    timeout-minutes: 5\n", "    timeout-minutes: 6\n")
RELEASE_LINE = edit(RELEASE, "\njobs:\n", "\n# planted\njobs:\n")
BUILDS_TWICE = edit(
    RELEASE,
    "      - name: Lock file is current (ADR-0001-C1)\n",
    "      - name: planted\n        run: docker build -t planted .\n"
    "      - name: Lock file is current (ADR-0001-C1)\n",
)


def drop_job(path: str, job: str) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        start = text.index(f"\n  {job}:\n") + 1
        following = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start:])
        end = start + following.start() + 1 if following else len(text)
        repo.put(path, repo.blob(text[:start] + text[end:]), mode)

    return change


def both(*changes: Callable[[Throwaway], None]) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        for apply in changes:
            apply(repo)

    return change


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    monkeypatch.delenv("CHANGESET_BASE", raising=False)
    return Throwaway(tmp_path / "repo", PR_146057A, monkeypatch)


def rewrite(throwaway: Throwaway, path: str, old: str, new: str) -> None:
    file = throwaway.work / path
    text = file.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert old in text, (path, old)
    file.write_bytes(text.replace(old, new, 1).encode("utf-8"))


# The live change set: `ci.yml` with a step changed, `release.yml` with a line added ---------------

LIVE_STATES = {
    "committed-base-unset": ("committed", None),
    "committed-base-empty": ("committed", ""),
    "worktree-base-pair-base": ("worktree", "pair-base"),
    "worktree-base-pair-head": ("worktree", "pair-head"),
    "committed-base-pr-146057a": ("committed", PR_146057A),
    "worktree-base-missing-commit": ("worktree", ABSENT),
}
Pair = tuple[str, str, str]
CLAIMS: dict[str, tuple[Pair, Callable[[], None]]] = {
    "eko119-jobs": (EKO_1_19, m119.test_eko119_k03_every_existing_ci_job_is_byte_identical),
    "eko119-release": (EKO_1_19, m119.test_eko119_k06_release_workflow_unchanged),
    "eko115-jobs": (EKO_1_15, m115.test_eko115_k07_ci_jobs_and_steps_unchanged),
    "eko115-contrast-packages-read": (
        EKO_1_15,
        m115.test_eko115_k07_contrast_packages_read_is_allowed_on_a_record_reading_job,
    ),
    "eko115-pre-merge-unchanged": (
        EKO_1_15,
        lambda: b115.test_eko115_k07_ci_unchanged_holds_on_both_bases("pre-merge"),
    ),
    "eko115-pre-merge-contrast": (
        EKO_1_15,
        lambda: b115.test_eko115_k07_contrast_packages_read_on_a_record_job_on_both_bases(
            "pre-merge"
        ),
    ),
    "eko115-qa-login-token": (
        EKO_1_15,
        lambda: q115.test_eko115_k07_qa_contrast_the_login_token_as_allowed_passes_on_both_bases(
            "pre-merge"
        ),
    ),
    "eko120-retune-live": (
        EKO_1_20,
        lambda: m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job(
            "live", "runtime-longer"
        ),
    ),
    "eko120-retune-pre-merge": (
        EKO_1_15,
        lambda: m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job(
            "pre-merge", "backend-retuned"
        ),
    ),
    "eko120-other-change-live": (
        EKO_1_20,
        lambda: m120.test_eko120_qa_contrast_any_other_change_to_the_job_fails("live", "runs-on"),
    ),
    "eko120-text-retune-live": (
        EKO_1_20,
        lambda: m120.test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job(
            "live", "backend-value"
        ),
    ),
    "eko120-text-other-change-live": (
        EKO_1_20,
        lambda: m120.test_eko120_qa_contrast_any_other_line_change_fails("live", "runs-on"),
    ),
}


@pytest.fixture(scope="module")
def placed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Throwaway]:
    """The live tree with `ci.yml` step changed and a line added to `release.yml` (built once)."""
    built = {}
    for placement in ("committed", "worktree"):
        repo = Throwaway(tmp_path_factory.mktemp(placement) / "repo", PR_146057A)
        if placement == "committed":
            planted = repo.commit(PR_146057A, both(STEP_CHANGED, RELEASE_LINE))
            repo.checkout_files(planted, CI, RELEASE)
        else:
            repo.checkout_files(PR_146057A, CI, RELEASE)
            rewrite(repo, CI, LOCK_RUN, "        run: uv lock --locked --offline\n")
            rewrite(repo, RELEASE, "\njobs:\n", "\n# planted\njobs:\n")
        built[placement] = repo
    return built


def put_live_state(
    placed: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch, state: str, pair: Pair
) -> None:
    placement, base = LIVE_STATES[state]
    monkeypatch.delenv("CHANGESET_BASE", raising=False)
    if base is not None:
        recorded = {"pair-base": pair[1], "pair-head": pair[2]}
        monkeypatch.setenv("CHANGESET_BASE", recorded.get(base, base))
    placed[placement].select(monkeypatch)
    monkeypatch.setattr(k07, "REPO_ROOT", placed[placement].work)
    monkeypatch.setattr(m119, "REPO_ROOT", placed[placement].work)


@pytest.mark.parametrize("state", sorted(LIVE_STATES))
@pytest.mark.parametrize("claim", sorted(CLAIMS))
def test_eko123_workflow_claims_ignore_a_live_change_set_touching_the_same_files(
    claim: str, state: str, placed: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch
) -> None:
    pair, body = CLAIMS[claim]
    put_live_state(placed, monkeypatch, state, pair)
    assert k07.in_worktree(CI) != file_at(PR_146057A, CI), "precondition: ci.yml holds the plant"
    assert k07.in_worktree(RELEASE) != file_at(PR_146057A, RELEASE), "precondition: release.yml too"
    body()


# K-03: one change inside the pair ---------------------------------------------------------------

JOB_PLANTS = {
    "a-step-changed": STEP_CHANGED,
    "a-permission-changed": PERMISSION_CHANGED,
    "a-job-removed": drop_job(CI, "frontend"),
}


def planted_head(throwaway: Throwaway, pair: tuple[str, str, str], change: Any) -> str:
    return throwaway.commit(pair[2], change)


@pytest.mark.parametrize("case", sorted(JOB_PLANTS))
def test_eko123_eko119_job_claim_fails_on_one_change_inside_the_pair(
    case: str, throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, head = file_at(EKO_1_19[1], CI), file_at(EKO_1_19[2], CI)
    assert base is not None and head is not None
    m119.assert_existing_jobs_unchanged(base, head)
    planted = planted_head(throwaway, EKO_1_19, JOB_PLANTS[case])
    monkeypatch.setattr(m119.eko_1_19_pair, "__defaults__", (EKO_1_19[1], planted))
    with pytest.raises(AssertionError):
        m119.test_eko119_k03_every_existing_ci_job_is_byte_identical()


def test_eko123_eko119_release_claim_fails_on_one_line_changed_inside_the_pair(
    throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    m119.test_eko119_k06_release_workflow_unchanged()
    planted = planted_head(throwaway, EKO_1_19, RELEASE_LINE)
    assert file_at(planted, RELEASE) != file_at(EKO_1_19[2], RELEASE)
    monkeypatch.setattr(m119.eko_1_19_pair, "__defaults__", (EKO_1_19[1], planted))
    with pytest.raises(AssertionError):
        m119.test_eko119_k06_release_workflow_unchanged()


def test_eko123_eko119_job_claim_contrast_a_retuned_timeout_on_the_pair_passes(
    throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    planted = planted_head(throwaway, EKO_1_19, RETUNED)
    assert file_at(planted, CI) != file_at(EKO_1_19[2], CI), "precondition: the head changed"
    monkeypatch.setattr(m119.eko_1_19_pair, "__defaults__", (EKO_1_19[1], planted))
    m119.test_eko119_k03_every_existing_ci_job_is_byte_identical()


@pytest.mark.parametrize("case", sorted(JOB_PLANTS))
def test_eko123_eko115_job_claim_fails_on_one_change_inside_the_pair(
    case: str, throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    m115.test_eko115_k07_ci_jobs_and_steps_unchanged()
    planted = planted_head(throwaway, EKO_1_15, JOB_PLANTS[case])
    monkeypatch.setattr(m115.pair_base_and_head, "__defaults__", (EKO_1_15[1], planted))
    with pytest.raises(AssertionError):
        m115.test_eko115_k07_ci_jobs_and_steps_unchanged()
    # The pre-merge rows of the two-bases checks judge the same head.
    monkeypatch.setattr(b115, "EKO_1_15_HEAD", planted)
    with pytest.raises(AssertionError):
        b115.test_eko115_k07_ci_unchanged_holds_on_both_bases("pre-merge")
    with pytest.raises(AssertionError):
        m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job("pre-merge", "runtime-longer")


def test_eko123_eko120_retune_claim_fails_on_one_change_inside_the_pair(
    throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job("live", "runtime-longer")
    m120.test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job("live", "backend-value")
    planted = planted_head(throwaway, EKO_1_20, STEP_CHANGED)
    monkeypatch.setattr(m120, "EKO_1_20_HEAD", planted)
    with pytest.raises(AssertionError):
        m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job("live", "runtime-longer")
    with pytest.raises(AssertionError):
        m120.test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job("live", "backend-value")


@pytest.mark.parametrize("case", ["timeout-not-an-integer", "timeout-as-a-boolean"])
def test_eko123_eko120_retune_claim_contrast_a_bad_timeout_on_the_pair_stays_red(case: str) -> None:
    m120.test_eko120_qa_contrast_any_other_change_to_the_job_fails("live", case)
    m120.test_eko120_qa_contrast_any_other_change_to_the_job_fails("pre-merge", case)


def test_eko123_eko120_retune_claim_contrast_a_retuned_timeout_on_the_pair_passes(
    throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    planted = planted_head(throwaway, EKO_1_20, RETUNED)
    assert file_at(planted, CI) != file_at(EKO_1_20[2], CI), "precondition: the head changed"
    monkeypatch.setattr(m120, "EKO_1_20_HEAD", planted)
    m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job("live", "runtime-longer")
    m120.test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job("live", "backend-value")


# K-05: "builds once" stays judged on the live release.yml ---------------------------------------
# EKO-1-26 widened that live invariant to the five project images; its carrier is the dedicated
# EKO-1-23-visible function below, so the pair claims stay insensitive to the working tree while
# this half still fails on any live release.yml that builds twice or forgets an image of the
# current family.


def test_eko123_eko119_release_claim_still_fails_on_a_live_release_that_builds_twice(
    throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    throwaway.checkout_files(throwaway.commit(PR_146057A, BUILDS_TWICE), CI, RELEASE)
    monkeypatch.setattr(k07, "REPO_ROOT", throwaway.work)
    monkeypatch.setattr(m119, "REPO_ROOT", throwaway.work)
    assert "docker build -t planted" in (k07.in_worktree(RELEASE) or ""), "precondition: the plant"
    with pytest.raises(AssertionError, match="builds an image"):
        m119.test_eko126_k04_live_release_builds_the_five_project_images_once()


def test_eko123_eko119_release_claim_contrast_the_live_release_without_the_plant_passes() -> None:
    m119.test_eko126_k04_live_release_builds_the_five_project_images_once()


# K-04: the pair is the real one, and a missing commit fails ---------------------------------------


@pytest.mark.parametrize(
    ("number", "pair"),
    [(85, EKO_1_15), (96, EKO_1_19), (113, EKO_1_20)],
    ids=["pr-85", "pr-96", "pr-113"],
)
def test_eko123_workflow_claims_read_the_parents_of_the_prs_merge(
    number: int, pair: tuple[str, str, str]
) -> None:
    merge, base, head = pair
    assert git("log", "-1", "--format=%s", merge).startswith(f"Merge pull request #{number} ")
    parents = git("rev-parse", f"{merge}^1", f"{merge}^2").split()
    assert parents == [base, head]
    assert parents[0] != parents[1]
    assert git("merge-base", *parents).strip() == parents[0]


def test_eko123_workflow_claims_bind_to_the_recorded_pairs() -> None:
    assert (m115.EKO_1_15_BASE, m115.EKO_1_15_HEAD) == EKO_1_15[1:]
    assert (m119.EKO_1_19_BASE, m119.EKO_1_19_HEAD) == EKO_1_19[1:]
    assert (m120.EKO_1_20_BASE, m120.EKO_1_20_HEAD) == EKO_1_20[1:]
    assert vars(b115)["EKO_1_15_HEAD"] == EKO_1_15[2]
    for check, pair in ((m115.pair_base_and_head, EKO_1_15), (m119.eko_1_19_pair, EKO_1_19)):
        defaults = inspect.signature(check).parameters
        assert [defaults["base"].default, defaults["head"].default] == list(pair[1:])


def test_eko123_eko115_pre_merge_fixture_is_the_ci_of_the_pair_base() -> None:
    fixture = b115.PRE_MERGE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert fixture == file_at(EKO_1_15[1], CI)


def commit_is_absent() -> bool:
    found = subprocess.run(
        ["git", "cat-file", "-e", f"{ABSENT}^{{commit}}"], cwd=REPO_ROOT, capture_output=True
    )
    return found.returncode != 0


@pytest.mark.parametrize("side", ["base", "head"])
def test_eko123_workflow_claims_error_on_an_unavailable_commit(
    side: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert commit_is_absent(), "precondition: the commit is not in the object store"
    with pytest.raises(subprocess.CalledProcessError):
        m115.pair_base_and_head(**{side: ABSENT})
    with pytest.raises(subprocess.CalledProcessError):
        m119.eko_1_19_pair(CI, **{side: ABSENT})
    for check, pair in ((m115.pair_base_and_head, EKO_1_15), (m119.eko_1_19_pair, EKO_1_19)):
        defaults = (ABSENT, pair[2]) if side == "base" else (pair[1], ABSENT)
        monkeypatch.setattr(check, "__defaults__", defaults)
    monkeypatch.setattr(m120, "EKO_1_20_BASE" if side == "base" else "EKO_1_20_HEAD", ABSENT)
    bodies: list[Callable[[], None]] = [
        m119.test_eko119_k03_every_existing_ci_job_is_byte_identical,
        m119.test_eko119_k06_release_workflow_unchanged,
        m115.test_eko115_k07_ci_jobs_and_steps_unchanged,
        lambda: m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job(
            "live", "runtime-longer"
        ),
        lambda: m120.test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job(
            "live", "backend-value"
        ),
    ]
    if side == "head":
        # The pre-merge rows read the base from a fixture; only their head can be unavailable.
        monkeypatch.setattr(b115, "EKO_1_15_HEAD", ABSENT)
        bodies += [
            lambda: b115.test_eko115_k07_ci_unchanged_holds_on_both_bases("pre-merge"),
            lambda: (
                q115.test_eko115_k07_qa_contrast_the_login_token_as_allowed_passes_on_both_bases(
                    "pre-merge"
                )
            ),
            lambda: m120.test_eko120_qa_a_retuned_timeout_is_not_a_changed_job(
                "pre-merge", "runtime-longer"
            ),
        ]
    for body in bodies:
        with pytest.raises(subprocess.CalledProcessError):
            body()
