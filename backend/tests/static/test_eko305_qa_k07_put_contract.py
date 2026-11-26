"""EKO-3-05 K-07, QA (rule 12; D-6 X-4 A): the edit operation's request and 409 answer are judged
by the contract check, not only create's.

`CHECKED` pairs the frontend's `NipTakenProblem` only with `POST /api/customers 409` and its
`CustomerInput` with the `CustomerCreate` component, so a PUT bound to another request model, or a
PUT 409 declared with another schema, left every pair agreeing. Here the same comparison the check
runs is applied to the PUT's own request body and 409 answer of the document of this commit, and
a one-field drift of either fails it.
"""

from typing import Any

import pytest

from tests.support import frontend_contract as fc
from tests.support.api_surface import real_app

EDIT = "/api/customers/{customer_id}"
PUT_409 = fc.Pair(fc.CUSTOMERS, "NipTakenProblem", f"PUT {EDIT} 409", fc.RESPONSE)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    found: dict[str, Any] = real_app().openapi()
    return found


def put_findings(document: dict[str, Any], pair: fc.Pair) -> list[str]:
    files = fc.api_sources()
    target = fc.target_schema(document, pair.target)
    assert target is not None, f"the document has no {pair.target}"
    source = fc.read_file(files[pair.file])
    comparison = fc.Comparison(pair, source, document)
    front = fc.declared_type(source, pair.name)
    return comparison.compare(front, fc.schema_type(target), pair.name)


def test_eko305_qa_k07_the_put_409_agrees_with_the_frontends_nip_taken_problem(
    document: dict[str, Any],
) -> None:
    assert put_findings(document, PUT_409) == []


def test_eko305_qa_k07_the_put_409_is_the_component_create_409_is(
    document: dict[str, Any],
) -> None:
    put = fc.target_schema(document, f"PUT {EDIT} 409")
    post = fc.target_schema(document, "POST /api/customers 409")
    assert put == post == {"$ref": "#/components/schemas/NipTakenProblem"}


def test_eko305_qa_k07_the_put_body_is_the_component_customer_input_is_paired_with(
    document: dict[str, Any],
) -> None:
    [paired] = [p.target for p in fc.CHECKED if p.name == "CustomerInput"]
    body = document["paths"][EDIT]["put"]["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": f"#/components/schemas/{paired}"}


def test_eko305_qa_k07_contrast_a_one_field_drift_of_the_put_409_fails(
    document: dict[str, Any],
) -> None:
    drifted = {
        **document,
        "components": {
            **document["components"],
            "schemas": {
                **document["components"]["schemas"],
                "QaDrifted": {
                    "type": "object",
                    "properties": {"detail": {"type": "string"}},
                    "required": ["detail"],
                },
            },
        },
    }
    put = drifted["paths"][EDIT]["put"]
    drifted["paths"] = {
        **drifted["paths"],
        EDIT: {
            **drifted["paths"][EDIT],
            "put": {
                **put,
                "responses": {
                    **put["responses"],
                    "409": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/QaDrifted"}
                            }
                        }
                    },
                },
            },
        },
    }
    assert put_findings(drifted, PUT_409) != []
