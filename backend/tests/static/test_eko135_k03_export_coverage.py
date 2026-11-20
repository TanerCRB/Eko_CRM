"""EKO-1-35 K-03: an exported type in any file under `frontend/src/api/` that is neither checked
against the document nor on the closed frontend-only list fails, naming the type and its file
(D-6, G-2 A). Every file is enumerated, subdirectories included; the frontend is read as data.
"""

from collections.abc import Callable

import pytest

from tests.support import frontend_contract as fc

AUTH = "frontend/src/api/auth.ts"
CUSTOMERS = "frontend/src/api/customers.ts"
CLIENT = "frontend/src/api/client.ts"
REFERENCE = "frontend/src/api/reference.ts"
VISITS = "frontend/src/api/visits.ts"
VISIT_INTERFACE = "export interface VisitRecord {\n  id: string;\n}\n"
VISIT_ALIAS = "export type VisitRecord = { id: string };\n"


def sources() -> dict[str, str]:
    return dict(fc.api_sources())


def with_file(path: str, text: str) -> dict[str, str]:
    files = sources()
    files[path] = text
    return files


def appended(path: str, text: str) -> dict[str, str]:
    files = sources()
    files[path] = files[path] + "\n" + text
    return files


def names(problems: list[str], *parts: str) -> bool:
    return any(all(part in line for part in parts) for line in problems)


def test_eko135_k03_pristine_tree_is_covered() -> None:
    assert fc.coverage_findings(sources()) == []


def test_eko135_k03_frontend_only_list_is_exactly_the_gate_1_list() -> None:
    assert fc.FRONTEND_ONLY == {
        (AUTH, "SessionRead"),
        (AUTH, "LogoutResult"),
        (CUSTOMERS, "RejectedField"),
        (CUSTOMERS, "CreateResult"),
        (CUSTOMERS, "ReadResult"),
        (CUSTOMERS, "ListResult"),
        (CLIENT, "ApiResponse"),
        (CLIENT, "RequestOptions"),
        # EKO-3-02 (Issue #161): frontend-only result union of the reference client.
        (REFERENCE, "VoivodeshipsResult"),
    }


SUBDIRECTORY = "frontend/src/api/visits/types.ts"
PLANTS: dict[str, tuple[str, Callable[[], dict[str, str]]]] = {
    "in-a-copy-of-customers.ts": (CUSTOMERS, lambda: appended(CUSTOMERS, VISIT_INTERFACE)),
    "in-a-new-file": (VISITS, lambda: with_file(VISITS, VISIT_INTERFACE)),
    "as-a-type-alias": (VISITS, lambda: with_file(VISITS, VISIT_ALIAS)),
    "in-a-subdirectory": (SUBDIRECTORY, lambda: with_file(SUBDIRECTORY, VISIT_ALIAS)),
}


@pytest.mark.parametrize("case_id", sorted(PLANTS))
def test_eko135_k03_unlisted_type_fails_naming_type_and_file(case_id: str) -> None:
    path, build = PLANTS[case_id]
    assert names(fc.coverage_findings(build()), path, "VisitRecord"), case_id


@pytest.mark.parametrize("case_id", sorted(PLANTS))
def test_eko135_k03_same_type_on_the_list_passes(case_id: str) -> None:
    path, build = PLANTS[case_id]
    files = build()
    listed = fc.FRONTEND_ONLY | {(path, "VisitRecord")}
    assert fc.coverage_findings(files, listed) == [], case_id


def test_eko135_k03_twin_in_another_file_is_not_excused() -> None:
    files = with_file(VISITS, "export type ListResult = { kind: string };\n")
    assert names(fc.coverage_findings(files), VISITS, "ListResult")


def test_eko135_k03_a_file_without_exported_types_passes() -> None:
    text = "export function visitLabel(id: string): string {\n  return id;\n}\n"
    files = with_file(VISITS, text + "export const VISIT_LIMIT = 10;\n")
    assert fc.coverage_findings(files) == []


def test_eko135_k03_reexport_is_judged_at_the_declaring_file() -> None:
    files = appended(AUTH, 'export type { VisitRecord } from "./visits";\n')
    files[VISITS] = VISIT_INTERFACE
    problems = fc.coverage_findings(files)
    assert names(problems, VISITS, "VisitRecord")
    assert not names(problems, AUTH), problems
    listed = fc.FRONTEND_ONLY | {(VISITS, "VisitRecord")}
    assert fc.coverage_findings(files, listed) == []


UNREADABLE = {
    "default": "export default interface VisitRecord {\n  id: string;\n}\n",
    "enum": "export enum VisitKind {\n  Field,\n}\n",
    "const-enum": "export const enum VisitKind {\n  Field,\n}\n",
    "class": "export class Visit {}\n",
    "declare": "export declare type VisitRecord = { id: string };\n",
    "local-list": "type VisitRecord = { id: string };\nexport { VisitRecord };\n",
    "namespace": "export namespace Visits {\n  export type Id = string;\n}\n",
    "unterminated-comment": "/* a comment\nexport type VisitRecord = { id: string };\n",
}


@pytest.mark.parametrize("case_id", sorted(UNREADABLE))
def test_eko135_k03_an_export_it_cannot_classify_fails(case_id: str) -> None:
    assert names(fc.coverage_findings(with_file(VISITS, UNREADABLE[case_id])), VISITS), case_id


def test_eko135_k03_a_file_it_does_not_read_fails() -> None:
    files = with_file("frontend/src/api/visits.json", "{}\n")
    assert names(fc.coverage_findings(files), "frontend/src/api/visits.json")


def test_eko135_k03_a02_stale_frontend_only_entry_fails() -> None:
    """A-02: an entry naming a type its file no longer exports would excuse it if it came back."""
    files = sources()
    exported = "export interface RequestOptions"
    files[CLIENT] = files[CLIENT].replace(exported, "interface RequestOptions")
    assert names(fc.coverage_findings(files), CLIENT, "RequestOptions")
