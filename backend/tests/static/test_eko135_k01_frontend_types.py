"""EKO-1-35 K-01: each frontend type that mirrors a backend schema agrees with its component in
the OpenAPI document generated at this commit (ADR-0001 Constraint 3, checklist rule 12).

"Agrees" is G-A A: identical, except that a response field the frontend does not declare, a
request enum gaining a value, and a request field the frontend always sends becoming optional
pass. Component names decide the pairing (G-B A). The frontend files are read as data.
"""

import copy
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tests.support import frontend_contract as fc
from tests.support.api_surface import real_app
from tests.support.contract_tree import copied_tree, run_check

AUTH = "frontend/src/api/auth.ts"
CUSTOMERS = "frontend/src/api/customers.ts"
REFERENCE = "frontend/src/api/reference.ts"
REPS = "frontend/src/api/reps.ts"
Document = dict[str, Any]
Plant = Callable[[Document], None]


@cache
def _document() -> Document:
    return real_app().openapi()


def document() -> Document:
    return copy.deepcopy(_document())


def sources() -> dict[str, str]:
    return dict(fc.api_sources())


def planted(path: str, old: str, new: str, files: dict[str, str] | None = None) -> dict[str, str]:
    files = dict(sources() if files is None else files)
    assert files[path].count(old) == 1, (path, old)
    files[path] = files[path].replace(old, new)
    return files


def schema(doc: Document, name: str) -> dict[str, Any]:
    found: dict[str, Any] = doc["components"]["schemas"][name]
    return found


def rename(component: str, old: str, new: str) -> Plant:
    def apply(doc: Document) -> None:
        target = schema(doc, component)
        target["properties"] = {
            (new if key == old else key): value for key, value in target["properties"].items()
        }
        target["required"] = [new if key == old else key for key in target.get("required", [])]

    return apply


def drop(component: str, field: str) -> Plant:
    def apply(doc: Document) -> None:
        target = schema(doc, component)
        del target["properties"][field]
        target["required"] = [key for key in target.get("required", []) if key != field]

    return apply


def set_property(component: str, field: str, value: dict[str, Any], required: bool) -> Plant:
    def apply(doc: Document) -> None:
        target = schema(doc, component)
        target["properties"][field] = value
        names = [key for key in target.get("required", []) if key != field]
        target["required"] = [*names, field] if required else names

    return apply


def kind_enum(*values: str) -> Plant:
    def apply(doc: Document) -> None:
        schema(doc, "ContactIn")["properties"]["kind"]["enum"] = list(values)

    return apply


def judged(files: dict[str, str], *plants: Plant) -> list[str]:
    doc = document()
    for plant in plants:
        plant(doc)
    return fc.type_findings(files, doc)


def named(problems: list[str], *parts: str) -> bool:
    return any(all(part in line for part in parts) for line in problems)


# The checked set and the pristine tree ----------------------------------------------------------


def test_eko135_k01_checked_set_is_g_c() -> None:
    assert {(pair.file, pair.name, pair.target) for pair in fc.CHECKED} == {
        (AUTH, "SessionInfo", "SessionInfo"),
        (AUTH, "LoggedOut", "LoggedOut"),
        (AUTH, "Problem", "Problem"),
        (CUSTOMERS, "ContactKind", "ContactIn.kind"),
        (CUSTOMERS, "ContactInput", "ContactIn"),
        (CUSTOMERS, "CustomerInput", "CustomerCreate"),
        (CUSTOMERS, "ContactRecord", "ContactOut"),
        (CUSTOMERS, "CustomerRecord", "CustomerOut"),
        (CUSTOMERS, "CustomerSummary", "CustomerItem"),
        (CUSTOMERS, "CustomerList", "CustomerList"),
        (CUSTOMERS, "ValidationProblem", "POST /api/customers 422"),
        # EKO-3-02 (Issue #161): the voivodeship reference client.
        (REFERENCE, "VoivodeshipList", "VoivodeshipList"),
        (REFERENCE, "VoivodeshipEntry", "VoivodeshipOut"),
        # EKO-3-04 (Issue #215, Q-6 A): the list's search parameters the SPA sends.
        (CUSTOMERS, "CustomerListQuery", "GET /api/customers query"),
        # EKO-3-08 (Issue #216, G-4 A): the manager's list of reps.
        (REPS, "RepList", "RepList"),
        (REPS, "RepEntry", "RepEntry"),
    }


def test_eko135_k01_pristine_tree_agrees() -> None:
    assert fc.type_findings(sources(), document()) == []


# (a) D-2: the backend alone renames `SessionInfo.name`, judged on the regenerated document ------


SESSION_NAME_PY = ("    name: str | None", "    display_name: str | None")
SESSION_NAME_TS = ("  name: string | null;", "  display_name: string | null;")


def test_eko135_k01_backend_only_rename_fails_on_the_generated_document(tmp_path: Path) -> None:
    tree = copied_tree(tmp_path, {"backend/app/api/auth.py": SESSION_NAME_PY})
    result = run_check(tree)
    assert result.returncode != 0, result.stdout + result.stderr
    assert named(result.stdout.splitlines(), "SessionInfo against SessionInfo", "SessionInfo.name")


def test_eko135_k01_same_rename_on_both_sides_passes(tmp_path: Path) -> None:
    tree = copied_tree(
        tmp_path, {"backend/app/api/auth.py": SESSION_NAME_PY, AUTH: SESSION_NAME_TS}
    )
    result = run_check(tree)
    assert (result.returncode, result.stdout) == (0, ""), result.stdout + result.stderr


# (b) one planted drift per type, each on one side alone; the other side too passes ------------

# id: (backend plant, frontend edit (path, old, new), parts the finding names)
BACKEND_DRIFTS: dict[str, tuple[Plant, tuple[str, str, str], tuple[str, ...]]] = {
    "CustomerOut.country-renamed": (
        rename("CustomerOut", "country", "country_code"),
        (
            CUSTOMERS,
            "  country: string;\n  contacts: ContactRecord[];",
            "  country_code: string;\n  contacts: ContactRecord[];",
        ),
        ("CustomerRecord against CustomerOut", "CustomerRecord.country"),
    ),
    "ContactOut.note-non-nullable": (
        set_property("ContactOut", "note", {"type": "string", "title": "Note"}, True),
        (
            CUSTOMERS,
            "  kind: string;\n  value: string;\n  note: string | null;",
            "  kind: string;\n  value: string;\n  note: string;",
        ),
        ("ContactRecord against ContactOut", "ContactRecord.note"),
    ),
    "CustomerItem.id-removed": (
        drop("CustomerItem", "id"),
        (
            CUSTOMERS,
            "export interface CustomerSummary {\n  id: string;\n",
            "export interface CustomerSummary {\n",
        ),
        ("CustomerSummary against CustomerItem", "CustomerSummary.id"),
    ),
    "CustomerList.items-renamed": (
        rename("CustomerList", "items", "entries"),
        (CUSTOMERS, "  items: CustomerSummary[];", "  entries: CustomerSummary[];"),
        ("CustomerList against CustomerList", "CustomerList.items"),
    ),
    "LoggedOut.status-literal-changed": (
        set_property(
            "LoggedOut",
            "status",
            {"type": "string", "const": "signed_out", "title": "Status"},
            True,
        ),
        (AUTH, '  status: "logged_out";', '  status: "signed_out";'),
        ("LoggedOut against LoggedOut", "LoggedOut.status"),
    ),
    "Problem.detail-renamed": (
        rename("Problem", "detail", "message"),
        (
            AUTH,
            "export interface Problem {\n  detail: string;",
            "export interface Problem {\n  message: string;",
        ),
        ("Problem against Problem", "Problem.detail"),
    ),
    "ContactIn.kind-loses-email": (
        kind_enum("phone"),
        (
            CUSTOMERS,
            'export type ContactKind = "phone" | "email";',
            'export type ContactKind = "phone";',
        ),
        ("ContactKind against ContactIn.kind", '"email"'),
    ),
}


@pytest.mark.parametrize("case_id", sorted(BACKEND_DRIFTS))
def test_eko135_k01_backend_side_drift_fails_naming_type_and_field(case_id: str) -> None:
    plant, _, parts = BACKEND_DRIFTS[case_id]
    assert named(judged(sources(), plant), *parts), case_id


@pytest.mark.parametrize("case_id", sorted(BACKEND_DRIFTS))
def test_eko135_k01_backend_side_drift_made_on_both_sides_passes(case_id: str) -> None:
    plant, (path, old, new), _ = BACKEND_DRIFTS[case_id]
    assert judged(planted(path, old, new), plant) == [], case_id


# id: (frontend edit (path, old, new), backend plant, parts the finding names)
FRONTEND_DRIFTS: dict[str, tuple[tuple[str, str, str], Plant, tuple[str, ...]]] = {
    "SessionInfo.name-renamed": (
        (AUTH, *SESSION_NAME_TS),
        rename("SessionInfo", "name", "display_name"),
        ("SessionInfo against SessionInfo", "SessionInfo.display_name"),
    ),
    "ContactInput.kind-widened-with-fax": (
        (CUSTOMERS, "  kind: ContactKind;", '  kind: ContactKind | "fax";'),
        kind_enum("phone", "email", "fax"),
        ("ContactInput against ContactIn", "ContactInput.kind"),
    ),
    "CustomerRecord.contacts-renamed": (
        (CUSTOMERS, "  contacts: ContactRecord[];", "  contact_list: ContactRecord[];"),
        rename("CustomerOut", "contacts", "contact_list"),
        ("CustomerRecord against CustomerOut", "CustomerRecord.contact_list"),
    ),
    "ValidationProblem.detail-renamed": (
        (
            CUSTOMERS,
            "export interface ValidationProblem {\n  detail",
            "export interface ValidationProblem {\n  errors",
        ),
        rename("HTTPValidationError", "detail", "errors"),
        ("ValidationProblem against POST /api/customers 422", "ValidationProblem.errors"),
    ),
}


@pytest.mark.parametrize("case_id", sorted(FRONTEND_DRIFTS))
def test_eko135_k01_frontend_side_drift_fails_naming_type_and_field(case_id: str) -> None:
    (path, old, new), _, parts = FRONTEND_DRIFTS[case_id]
    assert named(judged(planted(path, old, new)), *parts), case_id


@pytest.mark.parametrize("case_id", sorted(FRONTEND_DRIFTS))
def test_eko135_k01_frontend_side_drift_made_on_both_sides_passes(case_id: str) -> None:
    (path, old, new), plant, _ = FRONTEND_DRIFTS[case_id]
    assert judged(planted(path, old, new), plant) == [], case_id


# Nothing compared is never a pass (G-B A, mutation 2) -----------------------------------------


def _without_component(name: str) -> Plant:
    def apply(doc: Document) -> None:
        del doc["components"]["schemas"][name]

    return apply


def _component_renamed(old: str, new: str) -> Plant:
    """The same wire shape under another component name, every `$ref` rewritten."""

    def apply(doc: Document) -> None:
        schemas = doc["components"]["schemas"]
        schemas[new] = schemas.pop(old)
        stack: list[Any] = [doc]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("$ref") == f"#/components/schemas/{old}":
                    node["$ref"] = f"#/components/schemas/{new}"
                stack += list(node.values())
            elif isinstance(node, list):
                stack += node

    return apply


def _without_create_422(doc: Document) -> None:
    del doc["paths"]["/api/customers"]["post"]["responses"]["422"]


def _without_kind(doc: Document) -> None:
    drop("ContactIn", "kind")(doc)


MISSING: dict[str, tuple[Plant, tuple[str, ...]]] = {
    "component-missing": (_without_component("SessionInfo"), ("SessionInfo against SessionInfo",)),
    "component-renamed-same-shape": (
        _component_renamed("CustomerItem", "CustomerRow"),
        ("CustomerSummary against CustomerItem", "no such component"),
    ),
    "create-422-missing": (_without_create_422, ("ValidationProblem against POST",)),
    "property-target-missing": (_without_kind, ("ContactKind against ContactIn.kind",)),
}


@pytest.mark.parametrize("case_id", sorted(MISSING))
def test_eko135_k01_missing_target_fails_and_says_so(case_id: str) -> None:
    plant, parts = MISSING[case_id]
    assert named(judged(sources(), plant), *parts), case_id


def test_eko135_k01_missing_frontend_declaration_fails_and_says_so() -> None:
    files = planted(AUTH, 'export interface LoggedOut {\n  status: "logged_out";\n}\n', "")
    assert named(judged(files), "LoggedOut", AUTH, "not declared")


SESSION_INFO = (
    "export interface SessionInfo {\n"
    "  subject: string;\n  name: string | null;\n  roles: Role[];\n}"
)
UNREADABLE = {
    "pick": 'export type SessionInfo = Pick<Full, "subject" | "name">;',
    "mapped": 'export type SessionInfo = { [K in "subject" | "name"]: string | null };',
    "intersection": "export type SessionInfo = { subject: string } & { name: string | null };",
    "generic": "export interface SessionInfo<T> {\n  subject: string;\n  name: T;\n}",
    "extends": "export interface SessionInfo extends Base {\n  subject: string;\n}",
    "any": "export interface SessionInfo {\n  subject: string;\n  name: any;\n}",
    "readonly": "export interface SessionInfo {\n  readonly subject: string;\n  name: string;\n}",
}


@pytest.mark.parametrize("case_id", sorted(UNREADABLE))
def test_eko135_k01_unreadable_declaration_fails_naming_the_type(case_id: str) -> None:
    files = planted(AUTH, SESSION_INFO, UNREADABLE[case_id])
    assert named(judged(files), "SessionInfo", "cannot read"), case_id


def test_eko135_k01_same_shape_written_as_a_type_alias_passes() -> None:
    alias = "export type SessionInfo = { subject: string; name: string | null; roles: Role[] };"
    assert judged(planted(AUTH, SESSION_INFO, alias)) == []


# Edges -----------------------------------------------------------------------------------------

NULLABLE_NAME = {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Name"}

FAILING_EDGES: dict[str, tuple[tuple[str, str, str] | None, Plant | None, tuple[str, ...]]] = {
    "frontend-drops-null": (
        (AUTH, "  name: string | null;", "  name: string;"),
        None,
        ("SessionInfo against SessionInfo", "SessionInfo.name"),
    ),
    "backend-makes-name-optional": (
        None,
        set_property("SessionInfo", "name", NULLABLE_NAME, False),
        ("SessionInfo against SessionInfo", "SessionInfo.name"),
    ),
    "frontend-case-twin": (
        (AUTH, "  name: string | null;", "  Name: string | null;"),
        None,
        ("SessionInfo against SessionInfo", "SessionInfo.Name"),
    ),
    "backend-case-twin": (
        None,
        rename("SessionInfo", "name", "Name"),
        ("SessionInfo against SessionInfo", "SessionInfo.name"),
    ),
    "frontend-literal-changed": (
        (AUTH, '  status: "logged_out";', '  status: "loggedOut";'),
        None,
        ("LoggedOut against LoggedOut", "LoggedOut.status"),
    ),
    "new-required-request-field": (
        None,
        set_property("CustomerCreate", "region", {"type": "string"}, True),
        ("CustomerInput against CustomerCreate", "region"),
    ),
    "frontend-optional-where-required": (
        (
            CUSTOMERS,
            "export interface CustomerInput {\n  name: string;",
            "export interface CustomerInput {\n  name?: string;",
        ),
        None,
        ("CustomerInput against CustomerCreate", "CustomerInput.name"),
    ),
    "frontend-sends-unknown-field": (
        (CUSTOMERS, "  contacts: ContactInput[];", "  contacts: ContactInput[];\n  owner: string;"),
        None,
        ("CustomerInput against CustomerCreate", "CustomerInput.owner"),
    ),
    "request-integer-sent-as-a-string": (
        None,
        set_property("ContactIn", "value", {"type": "integer"}, True),
        ("ContactInput against ContactIn", "ContactInput.value"),
    ),
}


@pytest.mark.parametrize("case_id", sorted(FAILING_EDGES))
def test_eko135_k01_edge_fails(case_id: str) -> None:
    edit, plant, parts = FAILING_EDGES[case_id]
    files = sources() if edit is None else planted(*edit)
    assert named(judged(files, *([] if plant is None else [plant])), *parts), case_id


def _described(doc: Document) -> None:
    schema(doc, "SessionInfo")["description"] = "Who is signed in."
    schema(doc, "SessionInfo")["properties"]["name"]["description"] = "The display name."


def _reordered(doc: Document) -> None:
    target = schema(doc, "CustomerOut")
    target["properties"] = dict(reversed(list(target["properties"].items())))
    target["required"] = list(reversed(target["required"]))


PASSING_EDGES: dict[str, tuple[tuple[str, str, str] | None, Plant | None]] = {
    "frontend-properties-reordered": (
        (
            AUTH,
            "  subject: string;\n  name: string | null;",
            "  name: string | null;\n  subject: string;",
        ),
        None,
    ),
    "backend-properties-reordered": (None, _reordered),
    "description-changed": (None, _described),
    "new-response-field": (
        None,
        set_property("CustomerOut", "owner", {"type": "string", "title": "Owner"}, True),
    ),
    "request-enum-gains-a-value": (None, kind_enum("phone", "email", "fax")),
    "request-field-becomes-optional-while-always-sent": (
        None,
        set_property("ContactIn", "value", {"type": "string", "maxLength": 1016}, False),
    ),
}


@pytest.mark.parametrize("case_id", sorted(PASSING_EDGES))
def test_eko135_k01_edge_passes(case_id: str) -> None:
    edit, plant = PASSING_EDGES[case_id]
    files = sources() if edit is None else planted(*edit)
    assert judged(files, *([] if plant is None else [plant])) == [], case_id


def test_eko135_k01_a03_new_optional_request_field_fails() -> None:
    """A-03: G-A A passes only the listed relaxations; a request field the frontend never sends
    is not one of them."""
    plant = set_property("CustomerCreate", "region", {"type": "string"}, False)
    assert named(judged(sources(), plant), "CustomerInput against CustomerCreate", "region")
