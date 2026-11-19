"""EKO-1-35 K-05: the task leaves the contract as it is (D-5): no file under `backend/app/` or
`backend/migrations/` changes, the document generated at the head equals the base's, and the
names `frontend/src/api/` exports are the base's.

Base: $CHANGESET_BASE, else origin/main (merge base, `test_k07_changeset`). These are claims
about EKO-1-35's change set: once the checker is in the base, a later change set is not this one
and the live checks have nothing to judge. The contrasts below never read the base.
"""

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.static.test_k07_changeset import at_base, changed_paths, merge_base
from tests.support import frontend_contract as fc
from tests.support.contract_tree import COPIED, copied_tree, generated_document
from tests.support.fixed_pair import archive_into
from tests.support.repo import git

CHECKER = "backend/tests/support/frontend_contract.py"
CONTRACT_DIRECTORIES = ("backend/app/", "backend/migrations/")
BACKEND_COPIED = tuple(path for path in COPIED if path.startswith("backend/"))
AUTH_PY = "backend/app/api/auth.py"
CUSTOMERS_PY = "backend/app/api/customers.py"
AUTH_TS = "frontend/src/api/auth.ts"
Document = dict[str, Any]


def is_eko135_change_set() -> bool:
    return at_base(CHECKER) is None


def contract_paths(changed: list[str]) -> list[str]:
    return [path for path in changed if path.startswith(CONTRACT_DIRECTORIES)]


def canonical(document: Any) -> str:
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def document_differences(base: Document, head: Document) -> list[str]:
    """Each top-level part, path and component whose canonical JSON differs, by name."""
    problems = []
    for key in sorted(set(base) | set(head)):
        if canonical(base.get(key)) == canonical(head.get(key)):
            continue
        if key in ("paths", "components") and isinstance(base.get(key), dict):
            inner_base, inner_head = base.get(key) or {}, head.get(key) or {}
            if key == "components":
                inner_base = inner_base.get("schemas") or {}
                inner_head = (inner_head or {}).get("schemas") or {}
            names = sorted(set(inner_base) | set(inner_head))
            changed = [
                n for n in names if canonical(inner_base.get(n)) != canonical(inner_head.get(n))
            ]
            problems += [f"{key}: {name} differs from the base" for name in changed]
            if changed:
                continue
        problems.append(f"{key} differs from the base")
    return problems


def export_differences(base: dict[str, str], head: dict[str, str]) -> list[str]:
    problems = []
    for path in sorted(set(fc.sources_in(base)) | set(fc.sources_in(head))):
        before = fc.exported_names(base[path]) if path in base else set()
        after = fc.exported_names(head[path]) if path in head else set()
        problems += [f"{path}: {name} no longer exported" for name in sorted(before - after)]
        problems += [f"{path}: {name} newly exported" for name in sorted(after - before)]
    return problems


# The live claims on this change set -----------------------------------------------------------


def test_eko135_k05_no_file_under_backend_app_or_migrations_changes() -> None:
    if not is_eko135_change_set():
        return
    assert contract_paths(changed_paths()) == []


def test_eko135_k05_head_document_equals_the_base_document(tmp_path: Path) -> None:
    if not is_eko135_change_set():
        return
    base = generated_document(archive_into(merge_base(), tmp_path / "base", *BACKEND_COPIED))
    head = generated_document(copied_tree(tmp_path / "head", {}))
    assert document_differences(base, head) == []


def api_files_at_base() -> dict[str, str]:
    listed = git("ls-tree", "-r", "--name-only", merge_base(), "--", fc.API_DIR).split()
    found = {path: at_base(path) for path in listed}
    return {path: text for path, text in found.items() if text is not None}


def test_eko135_k05_exported_names_equal_the_base() -> None:
    if not is_eko135_change_set():
        return
    assert export_differences(api_files_at_base(), fc.api_sources()) == []


# Contrasts, on planted inputs only ------------------------------------------------------------


def test_eko135_k05_a_planted_backend_path_fails_and_others_pass() -> None:
    planted = ["docs/PLAN.md", AUTH_PY, "backend/tests/static/x.py", "backend/application.txt"]
    assert contract_paths(planted) == [AUTH_PY]
    assert contract_paths(["backend/migrations/versions/x.py"]) != []


@pytest.fixture(scope="module")
def pristine(tmp_path_factory: pytest.TempPathFactory) -> Document:
    return generated_document(copied_tree(tmp_path_factory.mktemp("pristine"), {}))


BACKEND_EDITS = {
    "SessionInfo.name-renamed": (AUTH_PY, ("    name: str | None", "    display_name: str | None")),
    "country-enum-dropped": (
        CUSTOMERS_PY,
        (', json_schema_extra={"enum": sorted(rules.COUNTRY_CODES)}', ""),
    ),
}


@pytest.mark.parametrize("case_id", sorted(BACKEND_EDITS))
def test_eko135_k05_a_planted_backend_edit_changes_the_generated_document(
    case_id: str, tmp_path: Path, pristine: Document
) -> None:
    path, edit = BACKEND_EDITS[case_id]
    edited = generated_document(copied_tree(tmp_path, {path: edit}))
    assert document_differences(pristine, edited) != [], case_id
    assert contract_paths([path]) == [path]


def test_eko135_k05_a_description_change_counts_and_identity_passes(pristine: Document) -> None:
    described = copy.deepcopy(pristine)
    described["components"]["schemas"]["SessionInfo"]["description"] = "Who is signed in."
    assert document_differences(pristine, described) != []
    assert document_differences(pristine, copy.deepcopy(pristine)) == []


def test_eko135_k05_a_document_that_cannot_be_generated_fails(tmp_path: Path) -> None:
    tree = copied_tree(tmp_path, {AUTH_PY: ("class SessionInfo(BaseModel):", "class SessionInfo(")})
    with pytest.raises(subprocess.CalledProcessError):
        generated_document(tree)


def _auth(old: str, new: str) -> dict[str, str]:
    files = dict(fc.api_sources())
    assert files[AUTH_TS].count(old) == 1, old
    files[AUTH_TS] = files[AUTH_TS].replace(old, new)
    return files


LOGGED_OUT = 'export interface LoggedOut {\n  status: "logged_out";\n}\n'


@pytest.mark.parametrize(
    "edit",
    [
        (LOGGED_OUT, ""),
        ("export interface LoggedOut {", "export interface SignedOut {"),
        ("export interface LoggedOut {", "interface LoggedOut {"),
    ],
    ids=["removed", "renamed", "no-longer-exported"],
)
def test_eko135_k05_a_changed_export_fails(edit: tuple[str, str]) -> None:
    assert export_differences(dict(fc.api_sources()), _auth(*edit)) != []


def test_eko135_k05_a_comment_only_edit_keeps_the_exports() -> None:
    files = _auth("// Shapes of", "// The shapes of")
    assert export_differences(dict(fc.api_sources()), files) == []
