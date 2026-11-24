"""EKO-1-40 (#228) K-05 and K-06, QA: the guarded-line check and the path check
(`tests.support.eko140_guards`), judged on planted pairs and on the task's own pinned pair.

Not a runtime test (no marker): it runs in the backend job's default `pytest`, beside the runtime
files it guards, so that it stays inside K-06's allowed set (`backend/tests/runtime/eko201/**`).

Every plant lives in a throwaway repository (`tests.support.fixed_pair.Throwaway`) on top of the
change under test, and is judged on both bases: the task's pre-task base `PRE_TASK` and the task's
own checkpoint `TASK_HEAD`. Nothing here reads the live PR base, origin/main, HEAD or the working
tree, so the verdict does not depend on which base the live branch has (EKO-1-10). A later main
that already holds the plant gives an empty difference: both checks are inert after merge. The
pinned commits (`PINNED` = `b099acc`, `PRE_TASK`, `TASK_HEAD`) are reachable in CI's checkout,
which fetches the full history (`fetch-depth: 0`).

K-05's mutation is shown item by item: each guarded item has a plant that only that item names,
and the same plant passes once that item is removed from the check.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.support import eko140_guards as guards
from tests.support.fixed_pair import Throwaway, add, delete, edit, leaked, rename, snapshot
from tests.support.repo import git

# Copied from `git rev-parse`, never typed by hand: the task's base when it started (#228's
# task-started event) and the checkpoint QA verified.
PRE_TASK = "5ac1a364393f890351b9e3419060e5edfbf30442"
TASK_HEAD = "7d4de9b604a34d47cc8efbf6531104e5d2eb63b9"
# The PR's merge base with main at the checkpoint (origin/main when QA ran).
TASK_BASE = "4b7c2e49ef9a2d9337c6287caa5606c1d3c538dd"
BASES = (PRE_TASK, TASK_HEAD)

CARRIER = guards.CARRIER
PROCESSES = guards.PROCESSES
OBSERVED_APP = guards.OBSERVED_APP
FIXTURE_APP = guards.FIXTURE_APP
DELAYED = "tests.support.eko140_checkout_delay:create_delayed_on_holder"
TASK_FILES = (
    "backend/tests/runtime/eko201/test_eko140_k01_checkout_delay.py",
    "backend/tests/support/eko140_checkout_delay.py",
    "backend/tests/support/eko140_signature.py",
    "docs/evidence/EKO-1-40/README.md",
    "docs/cost-register/2026-11-23_EKO-1-40_code_developer-backend_2.json",
)
Change = Callable[[Throwaway], None]


@pytest.fixture
def real_repository_untouched() -> Iterator[None]:
    """The plants leave this worktree, its HEAD and the plant refs alone (as EKO-1-23 K-07)."""
    before = snapshot()
    yield
    assert leaked(before, snapshot()) == []


@pytest.fixture
def repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_repository_untouched: None
) -> Throwaway:
    """Selected for every git call of the checks; nothing is written to the real repository."""
    return Throwaway(tmp_path / "repo", TASK_HEAD, monkeypatch)


def replaced_once(path: str, old: str, new: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        if text.count(old) != 1:
            raise ValueError(f"{path}: {old!r} occurs {text.count(old)} times, not once")
        repo.put(path, repo.blob(text.replace(old, new)), mode)

    return change


def appended(path: str, lines: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        repo.put(path, repo.blob(repo.text(path) + lines), mode)

    return change


def copied_from_task(path: str) -> Change:
    """`path` as the task's checkpoint holds it (a no-op on the checkpoint itself)."""

    def change(repo: Throwaway) -> None:
        mode, _, oid = git("ls-tree", TASK_HEAD, "--", path).split("\t")[0].split(" ")
        repo.put(path, oid, mode)

    return change


def changes(*each: Change) -> Change:
    def change(repo: Throwaway) -> None:
        for one in each:
            one(repo)

    return change


# The task's change set, replayed on either base: its files as the checkpoint holds them and one
# added plan line. On `TASK_HEAD` only the plan line is new.
CHANGE_UNDER_TEST = changes(
    *(copied_from_task(path) for path in TASK_FILES),
    appended("docs/PLAN.md", "\n- [ ] **EKO-9-99** — A planted reservation.\n"),
)


def head_with(repo: Throwaway, base: str, plant: Change) -> str:
    return repo.commit(repo.commit(base, CHANGE_UNDER_TEST), plant)


def later_main(repo: Throwaway, holding: str) -> str:
    """A main after `holding` merged (fast-forward), with one unrelated commit on top."""
    return repo.commit(holding, add("docs/after.md"))


# K-05 --------------------------------------------------------------------------------------------

RUN_LINE = "    run = pool_exhausted_responsive(pg, stub, all_waiting, late)\n"
RETRIED_RUN = """\
    for attempt in range(3):
        try:
            run = pool_exhausted_responsive(pg, stub, all_waiting, late)
            break
        except AssertionError:
            if attempt == 2:
                raise
"""
RETRYING_FIND = '''

class RetryingStore(ObservedStore):
    """Planted: a fixture `find` that retries on StorageUnavailable."""

    def find(self, session_hash: str) -> StoredSession | None:
        while True:
            try:
                return super().find(session_hash)
            except StorageUnavailable:
                time.sleep(0.1)
'''
CARRIER_TAIL = (
    "    assert len(stub.refreshes(sid)) == 1\n"
    "    assert stub.superseded_uses() == []\n"
    "    assert session_count(pg) == 1\n"
    "    # EKO-1-38"
)
CARRIER_DECORATOR = (
    '@pytest.mark.parametrize("late", [None, LATE_SECONDS], ids=["on-time", "one-late"])\n'
    "def test_k04_pool_exhausted"
)
BACKEND_ENV = (
    "    pg: Postgres, stub: oidc_stub.Stub, pool_size: int = 2, "
    "extra: dict[str, str] | None = None\n) -> dict[str, str]:"
)
CALL = (
    "    with backends(pg, stub, factory=factory) as (a, b):\n"
    "        session, sid = expired_session(stub, a)\n"
    "        stub.refresh_delay_seconds = 2.0"
)


def in_carrier(old: str, new: str) -> Change:
    return replaced_once(CARRIER, old, new)


# One edit inside each neighbouring function, in the order of `guards.NEIGHBOURS`.
NEIGHBOUR_EDITS = (
    ("stub.refresh_delay_seconds = 1.0", "stub.refresh_delay_seconds = 0.5"),
    (
        "with backends(pg, stub, count=1) as (a,):",
        "with backends(pg, stub, count=1, pool_size=3) as (a,):",
    ),
    (
        "assert [o.status for o in outcomes] == [503] * 10, outcomes",
        "assert [o.status for o in outcomes].count(503) >= 9, outcomes",
    ),
    ("        block(a, 1)\n        block(b, 2)\n", "        block(a, 1)\n        block(b, 1)\n"),
    ("assert len(outcomes) == 11", "assert len(outcomes) >= 10"),
    ("o.seconds >= BOUND]", "o.seconds >= BOUND - 1]"),
    ("assert elapsed < 3.5, elapsed", "assert elapsed < 4.5, elapsed"),
)


# One plant per guarded item; the criterion's six contrasts are marked (K-05 contrast).
PLANTS: dict[str, Change] = {
    "ten-statuses-200": in_carrier(
        "assert [o.status for o in outcomes] == [200] * 10, outcomes",
        "assert [o.status for o in outcomes].count(200) >= 9, outcomes",
    ),
    "one-refresh": in_carrier(
        CARRIER_TAIL, CARRIER_TAIL.replace("refreshes(sid)) == 1", "refreshes(sid)) <= 2")
    ),
    "no-superseded": in_carrier(
        CARRIER_TAIL,
        CARRIER_TAIL.replace("superseded_uses() == []", "superseded_uses().count(None) == 0"),
    ),
    "one-session-row": in_carrier(
        CARRIER_TAIL, CARRIER_TAIL.replace("session_count(pg) == 1", "session_count(pg) <= 2")
    ),
    "refresh-at-block": in_carrier(
        "assert run.refresh_at_block == [None], (refresh, run.marks)",
        "assert len(run.refresh_at_block) == 1, (refresh, run.marks)",
    ),
    "pools-full": in_carrier(
        "assert all(c == p and h == p for c, h, p in full.values()), full",
        "assert all(c >= p - 1 for c, h, p in full.values()), full",
    ),
    "hold-after-precondition": in_carrier(
        "assert hold_after(run, first) >= POOL_TIMEOUT_SECONDS,",
        "assert hold_after(run, first) >= POOL_TIMEOUT_SECONDS / 2,",
    ),
    "observed-precondition": in_carrier("and waiting == WAITERS:", "and waiting >= WAITERS - 1:"),
    # K-05 contrast: BOUND = 7.0.
    "bound": in_carrier("\nBOUND = 6.0\n", "\nBOUND = 7.0\n"),
    # K-05 contrast: WAITERS = 8.
    "waiters": in_carrier("\nWAITERS = 9\n", "\nWAITERS = 8\n"),
    "refresh-delay": in_carrier(
        "stub.refresh_delay_seconds = 2.0\n        with ThreadPoolExecutor",
        "stub.refresh_delay_seconds = 3.0\n        with ThreadPoolExecutor",
    ),
    "hold": in_carrier(
        "time.sleep(max(0.0, 1.5 - (time.monotonic() - started)))",
        "time.sleep(max(0.0, 2.5 - (time.monotonic() - started)))",
    ),
    "all-waiting-deadline": in_carrier(
        "    deadline = time.monotonic() + 10\n    while True:",
        "    deadline = time.monotonic() + 20\n    while True:",
    ),
    # K-05 contrast: pool_size=3.
    "carrier-backends-call": in_carrier(
        CALL, CALL.replace("factory=factory)", "factory=factory, pool_size=3)")
    ),
    "pool-size-default": replaced_once(PROCESSES, BACKEND_ENV, BACKEND_ENV.replace("= 2,", "= 3,")),
    "max-overflow": replaced_once(
        PROCESSES, "**pg.app_env(pool_size, 0),", "**pg.app_env(pool_size, 1),"
    ),
    "observed-factory": in_carrier(guards.OBSERVED, f'OBSERVED = "{DELAYED}"'),
    "default-factory": in_carrier(
        "late: float | None, factory: str = OBSERVED", "late: float | None, factory: str = BLOCKERS"
    ),
    "carrier-call": in_carrier(RUN_LINE, RUN_LINE.replace("late)", f'late, "{DELAYED}")')),
    # K-05 contrast (G-A A): one request sent after the 2.0-s refresh has been answered.
    "send-order": in_carrier(
        "pool.submit(send_tagged, t, session, i, stub, late, started)",
        "pool.submit(send_tagged, t, session, i, stub, 2.5, started)",
    ),
    "send-tagged": in_carrier(
        "time.sleep(max(0.0, anchor + late - time.monotonic()))",
        "time.sleep(max(0.0, anchor + late + 2.5 - time.monotonic()))",
    ),
    **{
        f"neighbour:{name}": in_carrier(old, new)
        for name, (old, new) in zip(guards.NEIGHBOURS, NEIGHBOUR_EDITS, strict=True)
    },
    **{
        f"eko138:{path.rsplit('/', 1)[1]}": edit(path, "assert ", "assert True or ")
        for path in guards.EKO138_TESTS
    },
    "additions-only:eko138_observed_app": replaced_once(
        OBSERVED_APP, "REFRESH_LAG_SECONDS = 0.2", "REFRESH_LAG_SECONDS = 0.4"
    ),
    "additions-only:eko201_fixture_app": replaced_once(
        FIXTURE_APP, "deadline = time.monotonic() + 10", "deadline = time.monotonic() + 20"
    ),
    # K-05 contrast: a retry of `pool_exhausted_responsive`.
    "no-retry-around-the-run": in_carrier(RUN_LINE, RETRIED_RUN),
    "no-rerun": in_carrier(CARRIER_DECORATOR, "@pytest.mark.flaky(reruns=3)\n" + CARRIER_DECORATOR),
    # K-05 contrast: a fixture `find` that retries on StorageUnavailable (lines added only).
    "no-retrying-find": appended(OBSERVED_APP, RETRYING_FIND),
}


def test_eko140_qa_k05_every_guarded_item_has_exactly_one_plant() -> None:
    assert sorted(PLANTS) == sorted(item.name for item in guards.ITEMS)


@pytest.mark.parametrize("base", BASES, ids=["pre-task-base", "task-head"])
def test_eko140_qa_k05_the_change_under_test_passes_and_is_inert_after_merge(
    base: str, repo: Throwaway
) -> None:
    head = repo.commit(base, CHANGE_UNDER_TEST)
    assert guards.guard_violations(base, head) == []
    assert guards.guard_violations(later_main(repo, head), head) == []


@pytest.mark.parametrize("base", BASES, ids=["pre-task-base", "task-head"])
@pytest.mark.parametrize("name", sorted(PLANTS))
def test_eko140_qa_k05_each_plant_is_named_by_its_item_only_and_passes_without_it(
    name: str, base: str, repo: Throwaway
) -> None:
    head = head_with(repo, base, PLANTS[name])
    found = guards.guard_violations(base, head)
    assert found, name
    assert all(problem.startswith(f"[{name}] ") for problem in found), found
    # The mutation, item by item: without this item the check lets its plant pass.
    others = tuple(item for item in guards.ITEMS if item.name != name)
    assert guards.guard_violations(base, head, others) == []
    assert guards.guard_violations(later_main(repo, head), head) == []


def test_eko140_qa_k05_k06_the_task_pair_passes() -> None:
    """The checkpoint QA verified, against the PR's merge base with main (no plant)."""
    assert guards.guard_violations(TASK_BASE, TASK_HEAD) == []
    assert guards.path_violations(TASK_BASE, TASK_HEAD) == []


# K-06 --------------------------------------------------------------------------------------------


def outside(status: str, path: str) -> str:
    return f"{status} {path}: {guards.OUTSIDE}"


def forbidden(path: str, prefix: str) -> str:
    return f"{path}: forbidden ({prefix}), which this change may not touch"


DATABASE = "backend/app/data/database.py"
CONFTEST = "backend/tests/runtime/conftest.py"
SIGNATURE = "backend/tests/support/eko140_signature.py"
# Each plant on top of the change under test, and exactly what the check says on either base.
PATH_PLANTS: dict[str, tuple[Change, list[str]]] = {
    # K-06 contrasts: the three the criterion names.
    "database-one-line": (
        edit(DATABASE, "POOL_TIMEOUT_SECONDS = 0.5", "POOL_TIMEOUT_SECONDS = 1.0"),
        [outside("M", DATABASE), forbidden(DATABASE, "backend/app/")],
    ),
    "runtime-conftest-one-line": (
        edit(CONFTEST, "UP_TIMEOUT_SECONDS = 900", "UP_TIMEOUT_SECONDS = 1200"),
        [outside("M", CONFTEST), forbidden(CONFTEST, CONFTEST)],
    ),
    "frontend-file-added": (
        add("frontend/src/planted.ts"),
        [
            outside("A", "frontend/src/planted.ts"),
            forbidden("frontend/src/planted.ts", "frontend/"),
        ],
    ),
    # Edges: a file added under backend/app/; a rename from an allowed path into a forbidden one.
    "backend-app-file-added": (
        add("backend/app/planted.py"),
        [
            outside("A", "backend/app/planted.py"),
            forbidden("backend/app/planted.py", "backend/app/"),
        ],
    ),
    "renamed-into-backend-app": (
        rename(SIGNATURE, "backend/app/eko140_signature.py"),
        [
            outside("A", "backend/app/eko140_signature.py"),
            forbidden("backend/app/eko140_signature.py", "backend/app/"),
        ],
    ),
    "migration-added": (
        add("backend/migrations/versions/planted.py"),
        [
            outside("A", "backend/migrations/versions/planted.py"),
            forbidden("backend/migrations/versions/planted.py", "backend/migrations/"),
        ],
    ),
    "rerun-plugin-in-pyproject": (
        edit(
            "backend/pyproject.toml",
            '"pytest>=8.4",',
            '"pytest>=8.4",\n    "pytest-rerunfailures",',
        ),
        [outside("M", "backend/pyproject.toml")],
    ),
    "other-test-directory": (
        add("backend/tests/static/test_eko140_planted.py"),
        [outside("A", "backend/tests/static/test_eko140_planted.py")],
    ),
    "other-support-module": (
        edit("backend/tests/support/oidc_stub.py", '"""', '"""Planted. '),
        [outside("M", "backend/tests/support/oidc_stub.py")],
    ),
    "doc-outside-the-evidence": (add("docs/planted.md"), [outside("A", "docs/planted.md")]),
    "plan-line-edited": (
        edit("docs/PLAN.md", "## EKO-2 — Access\n", "## EKO-2 — Access (edited)\n"),
        ["M docs/PLAN.md: may change by added lines only; 1 line(s) removed or changed"],
    ),
    "fixture-app-deleted": (delete(FIXTURE_APP), [outside("D", FIXTURE_APP)]),
    # Allowed: these pass.
    "fixture-app-lines-added": (appended(FIXTURE_APP, "\n# planted\n"), []),
    "new-eko140-support-module": (add("backend/tests/support/eko140_planted.py"), []),
    "new-eko201-runtime-file": (add("backend/tests/runtime/eko201/test_eko140_planted.py"), []),
    "evidence-file-added": (add("docs/evidence/EKO-1-40/planted.md"), []),
    "cost-row-added": (add("docs/cost-register/2026-11-23_EKO-1-40_planted.json"), []),
}


@pytest.mark.parametrize("base", BASES, ids=["pre-task-base", "task-head"])
def test_eko140_qa_k06_the_change_under_test_passes_and_is_inert_after_merge(
    base: str, repo: Throwaway
) -> None:
    head = repo.commit(base, CHANGE_UNDER_TEST)
    assert guards.path_violations(base, head) == []
    assert guards.path_violations(later_main(repo, head), head) == []


@pytest.mark.parametrize("base", BASES, ids=["pre-task-base", "task-head"])
@pytest.mark.parametrize("case", sorted(PATH_PLANTS))
def test_eko140_qa_k06_each_plant_gives_exactly_its_findings_and_is_inert_after_merge(
    case: str, base: str, repo: Throwaway
) -> None:
    plant, expected = PATH_PLANTS[case]
    head = head_with(repo, base, plant)
    assert guards.path_violations(base, head) == expected
    assert guards.path_violations(later_main(repo, head), head) == []


@pytest.mark.parametrize(
    "pair",
    [
        (TASK_HEAD[:12], TASK_HEAD),
        (TASK_HEAD, TASK_HEAD.upper()),
        ("HEAD", TASK_HEAD),
    ],
    ids=["abbreviated", "upper-case", "a-ref"],
)
@pytest.mark.parametrize("check", sorted(guards.CHECKS))
def test_eko140_qa_k05_k06_a_pair_that_is_not_two_full_shas_cannot_be_judged(
    check: str, pair: tuple[str, str], repo: Throwaway
) -> None:
    with pytest.raises(guards.CannotJudge):
        guards.CHECKS[check](*pair)
    assert guards.main([check, *pair]) == 2


def test_eko140_qa_k05_k06_the_command_exits_1_on_a_plant_and_0_on_the_change_under_test(
    repo: Throwaway, capsys: pytest.CaptureFixture[str]
) -> None:
    head = repo.commit(PRE_TASK, CHANGE_UNDER_TEST)
    assert guards.main(["k05", PRE_TASK, head]) == 0
    assert guards.main(["k06", PRE_TASK, head]) == 0
    planted = repo.commit(head, PLANTS["bound"])
    assert guards.main(["k05", PRE_TASK, planted]) == 1
    assert guards.main(["k06", PRE_TASK, repo.commit(head, add("frontend/x.ts"))]) == 1
    out = capsys.readouterr().out
    assert "[bound]" in out and "frontend/x.ts" in out
    assert guards.main(["k07", PRE_TASK, head]) == 2
