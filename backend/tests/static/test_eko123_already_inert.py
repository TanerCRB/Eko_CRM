"""EKO-1-23 (#110): three change-set guards are already inert on a later branch. Each case takes its
base text from commit 146057a (never the live base), applies the edit a later branch would make,
and the existing guard returns nothing; the same edit against a base text without the guard's
condition is flagged, so the guard, not an empty check, is what lets the later branch pass.

Revival conditions (what would bring each check back to life for every following branch):
- candidate 8: a merged task removes one of the two approved rows from the sensitive-paths register;
- candidate 9: `backend/tests/support/openapi_compat.py` is moved or renamed;
- candidate 12: none; the append-only ADR check keeps the EKO-1-06 marker in ADR-0002 for good.
"""

import pytest

from tests.static import test_k07_changeset as k07
from tests.support import changeset_checks as cc
from tests.support.fixed_pair import file_at

C_146057A = "146057a88b2ed2db658261690a5b420f7dfa2f8d"
REGISTER = k07.REGISTER
ADR_2 = f"{k07.ADR_DIR}/ADR-0002-database-and-migrations.md"
ADR_1 = f"{k07.ADR_DIR}/{k07.UNCHANGED_ADRS[0]}"


def base_text(path: str) -> str:
    text = file_at(C_146057A, path)
    assert text is not None, path
    return text


def without_approved_row(register: str) -> str:
    row = next(
        line
        for line in register.split("\n")
        if line.startswith("| `frontend/env-allowlist.json` |")
    )
    return register.replace(row + "\n", "", 1)


def unrelated_row_edited(register: str) -> str:
    line = next(line for line in register.split("\n") if line.startswith("| `**/Caddyfile*`"))
    edited = register.replace(line, line + " (edited)", 1)
    assert edited != register
    return edited


# Candidate 8 --------------------------------------------------------------------------------


def test_eko123_candidate8_register_check_already_inert_on_a_later_branch() -> None:
    base = base_text(REGISTER)
    head = unrelated_row_edited(base)
    assert head != base, "precondition: a later branch edited the register"
    assert cc.register_problems(base, head) == []


def test_eko123_candidate8_register_check_contrast_a_base_without_an_approved_row_is_flagged() -> (
    None
):
    base = without_approved_row(base_text(REGISTER))
    head = unrelated_row_edited(base)
    assert cc.register_problems(base, head) != []


# Candidate 9 --------------------------------------------------------------------------------


def with_added_package(manifest: str, lock: str) -> tuple[str, str]:
    added = manifest.replace(
        '    "pytest>=8.4",\n', '    "example-added>=1.0",\n    "pytest>=8.4",\n'
    )
    assert added != manifest, "precondition: the manifest at 146057a lists pytest"
    return added, lock + '\n[[package]]\nname = "example-added"\nversion = "1.0.0"\n'


def test_eko123_candidate9_package_check_already_inert_on_a_later_branch() -> None:
    base = (base_text("backend/pyproject.toml"), base_text("backend/uv.lock"))
    head = with_added_package(*base)
    comparator_in_base = file_at(C_146057A, cc.COMPARATOR) is not None
    assert comparator_in_base, "precondition: the comparator exists at 146057a"
    assert cc.package_additions(base, head, comparator_in_base) == []


def test_eko123_candidate9_package_check_contrast_a_base_without_the_comparator_is_flagged() -> (
    None
):
    base = (base_text("backend/pyproject.toml"), base_text("backend/uv.lock"))
    head = with_added_package(*base)
    assert cc.package_additions(base, head, comparator_in_base=False) != []


# Candidate 12 -------------------------------------------------------------------------------


def serve(monkeypatch: pytest.MonkeyPatch, texts: dict[str, str], planted: dict[str, str]) -> None:
    """The base reads from 146057a (with `texts` overriding it); the head holds `planted`."""
    monkeypatch.setattr(k07, "at_base", lambda path: texts.get(path, file_at(C_146057A, path)))
    monkeypatch.setattr(
        k07, "in_worktree", lambda path: planted.get(path, file_at(C_146057A, path))
    )


def marker_removed() -> dict[str, str]:
    adr = base_text(ADR_2)
    assert k07.EKO_1_06_MARKER in adr, "precondition: ADR-0002 at 146057a carries the marker"
    return {ADR_2: adr.replace(k07.EKO_1_06_MARKER, "### 2026-10-28 — without the marker", 1)}


def edited_register() -> dict[str, str]:
    return {REGISTER: unrelated_row_edited(base_text(REGISTER))}


def edited_adr() -> dict[str, str]:
    return {ADR_1: base_text(ADR_1) + "\nA later edit.\n"}


def test_eko123_candidate12_adr_0001_and_0006_check_already_inert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, {}, edited_adr())
    assert k07.at_base(ADR_1) != k07.in_worktree(ADR_1), "precondition: the head edits ADR-0001"
    k07.test_k07_adr_0001_and_0006_are_unchanged()


def test_eko123_candidate12_adr_check_contrast_a_base_without_the_marker_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, marker_removed(), edited_adr())
    with pytest.raises(AssertionError):
        k07.test_k07_adr_0001_and_0006_are_unchanged()


def test_eko123_candidate12_register_check_already_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, {}, edited_register())
    assert k07.at_base(REGISTER) != k07.in_worktree(REGISTER), "precondition: the head edits it"
    k07.test_k07_register_changes_only_by_the_two_approved_edits()


def test_eko123_candidate12_register_check_contrast_a_base_without_the_marker_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, marker_removed(), edited_register())
    with pytest.raises(AssertionError):
        k07.test_k07_register_changes_only_by_the_two_approved_edits()


@pytest.mark.parametrize("variant", sorted(k07.register_variants()))
def test_eko123_candidate12_register_edit_check_already_inert(
    variant: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve(monkeypatch, {}, {})
    k07.test_k07_register_check_fails_on_any_other_edit(variant)


def test_eko123_candidate12_register_edit_check_contrast_without_the_marker_reaches_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, marker_removed(), {})
    assert k07.is_eko_1_06_change_set(), "precondition: the marker is gone from the base"
    k07.test_k07_register_check_fails_on_any_other_edit("paragraph-edited")
