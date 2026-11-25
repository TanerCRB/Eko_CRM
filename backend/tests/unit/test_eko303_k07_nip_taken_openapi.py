"""EKO-3-03, the backend half of the contract K-07 reads (ADR-0001 Constraint 3; gate 1, A-2 A):
`POST /api/customers` documents its 409 as `NipTakenProblem`, `{detail: string}` required and
`existing_customer_id` an optional UUID that is never `null`, read from the OpenAPI document the
shipped `create_app()` serves. The frontend's hand-written type is checked against this schema by
`tests/support/frontend_contract.py` once it exists.
"""

from typing import Any

from tests.support.api_surface import real_app


def document() -> dict[str, Any]:
    found: dict[str, Any] = real_app().openapi()
    return found


def test_k07_the_create_operation_documents_its_409_as_nip_taken_problem() -> None:
    responses = document()["paths"]["/api/customers"]["post"]["responses"]
    schema = responses["409"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/NipTakenProblem"}


def test_k07_nip_taken_problem_is_a_required_detail_and_an_optional_never_null_uuid() -> None:
    schema = document()["components"]["schemas"]["NipTakenProblem"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["detail"]
    properties = schema["properties"]
    assert set(properties) == {"detail", "existing_customer_id"}
    assert properties["detail"]["type"] == "string"
    reference = properties["existing_customer_id"]
    assert (reference["type"], reference["format"]) == ("string", "uuid")
    assert "anyOf" not in reference and "null" not in str(reference)
