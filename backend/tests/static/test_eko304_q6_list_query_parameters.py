"""EKO-3-04, gate-1 decision Q-6 A (ADR-0001 Constraint 3, checklist rule 12): the query parameters
the SPA sends to `GET /api/customers` are checked against that operation's parameters in the OpenAPI
document generated at this commit. FastAPI ignores an unknown query parameter, so a name that
drifts on either side would answer the unfiltered list with every behavioural test green.

The SPA declares what it sends as `CustomerListQuery` in `frontend/src/api/customers.ts`, paired
with `GET /api/customers query`. A query type is judged as a request ("what the frontend sends is
accepted"), except that an optional parameter the SPA does not send passes: unlike a body field,
a query parameter left out is simply absent (C-1: the SPA sends no `owner`).

The pair is in `CHECKED` (and in EKO-1-35's pinned checked set), so the repository's own tree is
judged by every EKO-1-35 test; the contrasts below plant their edits on a copy of the tree.
"""

import copy
from functools import cache
from typing import Any

from tests.support import frontend_contract as fc
from tests.support.api_surface import real_app

CUSTOMERS = "frontend/src/api/customers.ts"
TARGET = "GET /api/customers query"
PAIR = fc.Pair(CUSTOMERS, "CustomerListQuery", TARGET, fc.QUERY)
DECLARATION = "export interface CustomerListQuery {"
SENDS_Q = "  q?: string;\n"
Document = dict[str, Any]


@cache
def _document() -> Document:
    return real_app().openapi()


def document() -> Document:
    return copy.deepcopy(_document())


def declaration_span(text: str) -> tuple[int, int]:
    """Start and end (past its closing `}` line) of the `CustomerListQuery` declaration."""
    start = text.index(DECLARATION)
    return start, text.index("}\n", start) + 2


def without_query_type() -> dict[str, str]:
    """The repository's frontend files with the `CustomerListQuery` declaration taken out."""
    files = dict(fc.api_sources())
    text = files[CUSTOMERS]
    if DECLARATION in text:
        start, end = declaration_span(text)
        text = text[:start] + text[end:]
    files[CUSTOMERS] = text
    return files


def with_query_type(body: str) -> dict[str, str]:
    """The repository's frontend files, with `CustomerListQuery` declared as `body`."""
    files = without_query_type()
    files[CUSTOMERS] += "\n" + DECLARATION + "\n" + body + "}\n"
    return files


def query_findings(files: dict[str, str], doc: Document | None = None) -> list[str]:
    assert PAIR in fc.CHECKED, "the pair is not checked"
    found = fc.type_findings(files, document() if doc is None else doc)
    return [line for line in found if "CustomerListQuery" in line]


def list_parameters(doc: Document) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = doc["paths"]["/api/customers"]["get"]["parameters"]
    return found


def test_q6_the_list_query_is_a_checked_pair() -> None:
    assert PAIR in fc.CHECKED


def test_q6_the_repositorys_own_spa_declaration_agrees() -> None:
    files = dict(fc.api_sources())
    assert DECLARATION in files[CUSTOMERS], "the SPA does not declare the type"
    assert query_findings(files) == []


def test_q6_contrast_the_spa_renaming_q_in_its_own_declaration_fails() -> None:
    files = dict(fc.api_sources())
    text = files[CUSTOMERS]
    start, end = declaration_span(text)
    declared = text[start:end]
    assert declared.count("q?: string;") == 1, declared
    renamed = declared.replace("q?: string;", "query?: string;")
    files[CUSTOMERS] = text[:start] + renamed + text[end:]
    problems = query_findings(files)
    assert any("CustomerListQuery.query" in line for line in problems), problems


def test_q6_contrast_the_type_not_declared_fails_and_says_so() -> None:
    problems = query_findings(without_query_type())
    assert any("not declared" in line for line in problems), problems


def test_q6_the_document_names_q_and_owner_as_optional_string_query_parameters() -> None:
    parameters = {p["name"]: p for p in list_parameters(document()) if p["in"] == "query"}
    assert sorted(parameters) == ["owner", "q", "state"]
    assert not any(p.get("required") for p in parameters.values())
    assert fc.target_schema(document(), TARGET) is not None


def test_q6_the_spa_sending_q_agrees() -> None:
    assert query_findings(with_query_type(SENDS_Q)) == []


def test_q6_every_other_pair_still_agrees_with_the_type_declared() -> None:
    assert fc.type_findings(with_query_type(SENDS_Q), document()) == []


def test_q6_contrast_the_spa_sending_another_name_fails_naming_it() -> None:
    problems = query_findings(with_query_type("  search?: string;\n"))
    assert any("CustomerListQuery.search" in line for line in problems), problems


def test_q6_contrast_the_backend_renaming_q_fails() -> None:
    doc = document()
    for parameter in list_parameters(doc):
        if parameter["name"] == "q":
            parameter["name"] = "query"
    problems = query_findings(with_query_type(SENDS_Q), doc)
    assert any("CustomerListQuery.q" in line for line in problems), problems


def test_q6_contrast_a_parameter_of_another_type_fails() -> None:
    problems = query_findings(with_query_type("  q?: number;\n"))
    assert any("CustomerListQuery.q" in line for line in problems), problems


def test_q6_an_optional_parameter_the_spa_does_not_send_passes_and_a_required_one_fails() -> None:
    assert query_findings(with_query_type(SENDS_Q + "  owner?: string;\n")) == []
    doc = document()
    for parameter in list_parameters(doc):
        if parameter["name"] == "owner":
            parameter["required"] = True
    problems = query_findings(with_query_type(SENDS_Q), doc)
    assert any("owner" in line and "required" in line for line in problems), problems


def test_q6_an_operation_with_no_such_query_fails_and_says_so() -> None:
    doc = document()
    del doc["paths"]["/api/customers"]["get"]
    problems = query_findings(with_query_type(SENDS_Q), doc)
    assert any("no such component" in line for line in problems), problems


def test_q6_a_header_or_path_parameter_is_not_a_query_parameter() -> None:
    doc = document()
    for parameter in list_parameters(doc):
        if parameter["name"] == "q":
            parameter["in"] = "header"
    problems = query_findings(with_query_type(SENDS_Q), doc)
    assert any("CustomerListQuery.q" in line for line in problems), problems
