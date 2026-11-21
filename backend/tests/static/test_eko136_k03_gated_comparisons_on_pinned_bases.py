"""EKO-1-36 (#214) K-03, K-04, K-06: the five live base comparisons of EKO-1-35 K-05/K-06/K-07 are
inert against a base that holds the checker and live against one without it (EKO-1-35 A-06).

Each case calls the existing function, as it is in this tree, with:
- the base: CHANGESET_BASE set to a pinned full SHA for the case, so `merge_base()` resolves to the
  pin whatever the environment carried (K-04); never the live origin/main or the PR base;
- the head: a throwaway repository (`fixed_pair.Throwaway`) holding WITH_CHECKER plus one plant,
  checked out in temporary space and selected for every git call; the readers bound to the real
  repository root (`in_worktree`, `copied_tree`, `api_sources`) are re-rooted at its working tree.

The head is WITH_CHECKER plus the plant against both pins. Against WITH_CHECKER it differs in
exactly the plant; against WITHOUT_CHECKER in EKO-1-35's own change set plus the plant, and
EKO-1-35 changed none of the judged files (its own K-05..K-07), so the plant is all a live
comparison finds. A case and its contrast differ in the pin alone. Plants live in temporary space
only; every case asserts that the real files they imitate and the real repository are unchanged
(K-06).
"""

import functools
import re
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.static import test_eko135_k05_contract_unchanged as k05
from tests.static import test_eko135_k06_rule7_untouched as k06
from tests.static import test_eko135_k07_runtime_dependencies as k07
from tests.static import test_k07_changeset as changeset
from tests.support import frontend_contract as fc
from tests.support.contract_tree import copied_tree, generated_document
from tests.support.fixed_pair import (
    ABSENT,
    Throwaway,
    archive_into,
    file_at,
    leaked,
    require_commit,
    snapshot,
)
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# PR #211 (EKO-1-35) merged as WITH_CHECKER; its first parent is the main it merged into.
WITH_CHECKER = "be0c5f73bc5d2b479ce912a2e398ffa663f6dee9"
WITHOUT_CHECKER = "9ea5d7e0ea777bb956ab2d482fe007519013b057"
PINS = (WITH_CHECKER, WITHOUT_CHECKER)
CHECKER = "backend/tests/support/frontend_contract.py"
AUTH_PY = "backend/app/api/auth.py"
AUTH_TS = "frontend/src/api/auth.ts"
SOURCE_CHECKS = "backend/tests/support/source_checks.py"
PACKAGE = "frontend/package.json"
PYPROJECT = "backend/pyproject.toml"
IMITATED = (AUTH_PY, AUTH_TS, SOURCE_CHECKS, PACKAGE, PYPROJECT)
API_SOURCES = fc.api_sources
LOGGED_OUT = 'export interface LoggedOut {\n  status: "logged_out";\n}\n'
Change = Callable[[Throwaway], None]


def replaced_once(path: str, old: str, new: str) -> Change:
    """`old` replaced in `path`; raises unless it occurs exactly once (never a silent no-op)."""

    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        if text.count(old) != 1:
            raise ValueError(f"{path}: {old!r} occurs {text.count(old)} times, not once")
        repo.put(path, repo.blob(text.replace(old, new)), mode)

    return change


def appended(path: str, line: str) -> Change:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        repo.put(path, repo.blob(repo.text(path) + line), mode)

    return change


PLANTS: dict[str, Change] = {
    "auth-py-name-renamed": replaced_once(
        AUTH_PY, "    name: str | None", "    display_name: str | None"
    ),
    "auth-ts-logged-out-removed": replaced_once(AUTH_TS, LOGGED_OUT, ""),
    "source-checks-exemption-appended": appended(
        SOURCE_CHECKS, "EXEMPT = ('frontend/src/api/',)\n"
    ),
    "package-runtime-dependency-added": replaced_once(
        PACKAGE, '"dependencies": {\n', '"dependencies": {\n    "left-pad": "1.3.0",\n'
    ),
}


@pytest.fixture(scope="module")
def heads(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Throwaway]:
    """One throwaway per plant, checked out at WITH_CHECKER plus that plant alone."""
    found = {}
    for name, change in PLANTS.items():
        repo = Throwaway(tmp_path_factory.mktemp(name), WITH_CHECKER)
        repo.checkout(repo.commit(WITH_CHECKER, change))
        found[name] = repo
    return found


def judge(monkeypatch: pytest.MonkeyPatch, head: Throwaway, pin: str) -> None:
    """The live comparisons read `pin` as the base and `head`'s working tree as the head."""
    assert re.fullmatch(r"[0-9a-f]{40}", pin) and require_commit(pin) == pin, pin
    head.select(monkeypatch)
    monkeypatch.setenv("CHANGESET_BASE", pin)
    monkeypatch.setattr(changeset, "REPO_ROOT", head.work)
    monkeypatch.setattr(k05, "copied_tree", functools.partial(copied_tree, source=head.work))
    monkeypatch.setattr(fc, "api_sources", functools.partial(API_SOURCES, head.work))


@contextmanager
def unchanged(root: Path = REPO_ROOT) -> Iterator[None]:
    """K-06: the real files the plants imitate, and the repository at `root`, are left as found."""
    files = {path: (root / path).read_bytes() for path in IMITATED}
    before = snapshot(root)
    yield
    assert {path: (root / path).read_bytes() for path in IMITATED} == files
    assert leaked(before, snapshot(root)) == []


# What each function judges, computed through its own head reader with the gate left out: the
# precondition that the plant reached it.


def changed_contract_paths(tmp_path: Path, head: Path) -> list[str]:
    return k05.contract_paths(changeset.changed_paths())


def document_differences(tmp_path: Path, head: Path) -> list[str]:
    base = archive_into(changeset.merge_base(), tmp_path / "base", *k05.BACKEND_COPIED)
    planted = copied_tree(tmp_path / "head", {}, source=head)
    return k05.document_differences(generated_document(base), generated_document(planted))


def export_differences(tmp_path: Path, head: Path) -> list[str]:
    return k05.export_differences(k05.api_files_at_base(), fc.api_sources())


def guard_differences(tmp_path: Path, head: Path) -> list[str]:
    base = {path: changeset.at_base(path) for path in k06.GUARD}
    return k06.guard_changes(base, {path: changeset.in_worktree(path) for path in k06.GUARD})


def dependency_differences(tmp_path: Path, head: Path) -> list[str]:
    package = (changeset.at_base(PACKAGE), changeset.in_worktree(PACKAGE))
    pyproject = (changeset.at_base(PYPROJECT), changeset.in_worktree(PYPROJECT))
    return k07.runtime_dependency_changes(package, pyproject)


# case: (the plant, the gated function called from its module at call time, what it judges, the
# text a live run must name)
CASES: dict[str, tuple[str, Callable[[Path], None], Callable[[Path, Path], list[str]], str]] = {
    "k05-paths": (
        "auth-py-name-renamed",
        lambda tmp: k05.test_eko135_k05_no_file_under_backend_app_or_migrations_changes(),
        changed_contract_paths,
        AUTH_PY,
    ),
    "k05-document": (
        "auth-py-name-renamed",
        lambda tmp: k05.test_eko135_k05_head_document_equals_the_base_document(tmp),
        document_differences,
        "components: SessionInfo differs",
    ),
    "k05-exports": (
        "auth-ts-logged-out-removed",
        lambda tmp: k05.test_eko135_k05_exported_names_equal_the_base(),
        export_differences,
        f"{AUTH_TS}: LoggedOut no longer exported",
    ),
    "k06-guard": (
        "source-checks-exemption-appended",
        lambda tmp: k06.test_eko135_k06_rule7_guard_is_identical_to_the_base(),
        guard_differences,
        SOURCE_CHECKS,
    ),
    "k07-dependencies": (
        "package-runtime-dependency-added",
        lambda tmp: k07.test_eko135_k07_runtime_dependencies_equal_the_base(),
        dependency_differences,
        f"{PACKAGE}: dependencies differ from the base",
    ),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_eko136_k03_each_gated_comparison_is_inert_against_a_base_with_the_checker(
    case: str, heads: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plant, call, judged, named = CASES[case]
    with unchanged():
        judge(monkeypatch, heads[plant], WITH_CHECKER)
        found = judged(tmp_path / "judged", heads[plant].work)
        assert any(named in difference for difference in found), f"precondition: {found}"
        call(tmp_path / "call")


@pytest.mark.parametrize("case", sorted(CASES))
def test_eko136_k03_contrast_each_is_live_against_a_base_without_the_checker(
    case: str, heads: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plant, call, _, named = CASES[case]
    with unchanged():
        judge(monkeypatch, heads[plant], WITHOUT_CHECKER)
        with pytest.raises(AssertionError) as raised:
            call(tmp_path / "call")
        assert named in str(raised.value), str(raised.value)


PLANTED_PATHS = {
    "auth-py-name-renamed": AUTH_PY,
    "auth-ts-logged-out-removed": AUTH_TS,
    "source-checks-exemption-appended": SOURCE_CHECKS,
    "package-runtime-dependency-added": PACKAGE,
}


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_eko136_k03_each_head_differs_from_the_pin_only_in_its_own_plant(
    plant: str, heads: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch
) -> None:
    with unchanged():
        judge(monkeypatch, heads[plant], WITH_CHECKER)
        assert changeset.changed_paths() == [PLANTED_PATHS[plant]]


# K-04 ----------------------------------------------------------------------------------------


def test_eko136_k04_the_pins_are_full_commits_one_with_the_checker_one_without() -> None:
    for pin in PINS:
        assert re.fullmatch(r"[0-9a-f]{40}", pin), pin
        assert require_commit(pin) == pin
    assert file_at(WITH_CHECKER, CHECKER) is not None
    assert file_at(WITHOUT_CHECKER, CHECKER) is None
    assert require_commit(f"{WITH_CHECKER}^1") == WITHOUT_CHECKER


def test_eko136_k04_an_absent_or_abbreviated_pin_is_never_a_base_without_the_checker() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        file_at(ABSENT, CHECKER)
    assert require_commit(WITH_CHECKER[:12]) != WITH_CHECKER[:12]


@pytest.mark.parametrize("environment", [None, WITHOUT_CHECKER, WITH_CHECKER, "HEAD"])
@pytest.mark.parametrize("pin", PINS)
def test_eko136_k04_the_pin_decides_the_base_whatever_the_environment_carries(
    pin: str,
    environment: str | None,
    heads: dict[str, Throwaway],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if environment is None:
        monkeypatch.delenv("CHANGESET_BASE", raising=False)
    else:
        monkeypatch.setenv("CHANGESET_BASE", environment)
    with unchanged():
        judge(monkeypatch, heads["source-checks-exemption-appended"], pin)
        assert changeset.merge_base().strip() == pin
        assert k06.is_eko135_change_set() is (pin == WITHOUT_CHECKER)


def test_eko136_k04_a_missing_base_raises_rather_than_passing_or_reading_as_live(
    heads: dict[str, Throwaway], monkeypatch: pytest.MonkeyPatch
) -> None:
    with unchanged():
        judge(monkeypatch, heads["source-checks-exemption-appended"], WITH_CHECKER)
        monkeypatch.setenv("CHANGESET_BASE", ABSENT)
        with pytest.raises(subprocess.CalledProcessError):
            k06.test_eko135_k06_rule7_guard_is_identical_to_the_base()


# K-06 ----------------------------------------------------------------------------------------


def test_eko136_k06_the_guard_fails_when_a_plant_reaches_a_real_file(tmp_path: Path) -> None:
    for path in IMITATED:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(b"as found\n")
    with pytest.raises(AssertionError):
        with unchanged(tmp_path):
            (tmp_path / AUTH_PY).write_bytes(b"as found\nplanted\n")
    with unchanged(tmp_path):
        (tmp_path / "elsewhere.txt").write_bytes(b"not a file a plant imitates\n")
