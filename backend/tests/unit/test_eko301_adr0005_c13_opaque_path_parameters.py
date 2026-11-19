"""EKO-3-01, ADR-0005-C13 (backend half): every path parameter in the backend's OpenAPI document
is an opaque record identifier, a UUID, so no customer field value can travel in a path.
Contrast: a document with a name-shaped path parameter fails the check.
"""

from typing import Any

from tests.support.api_surface import real_app

Document = dict[str, Any]


def path_parameter_problems(document: Document) -> list[str]:
    problems = []
    for path, item in document.get("paths", {}).items():
        shared = [p for p in item.get("parameters", []) if p.get("in") == "path"]
        for method, operation in item.items():
            if not isinstance(operation, dict) or method == "parameters":
                continue
            own = [p for p in operation.get("parameters", []) if p.get("in") == "path"]
            for parameter in [*shared, *own]:
                schema = parameter.get("schema", {})
                if (schema.get("type"), schema.get("format")) != ("string", "uuid"):
                    problems.append(f"{method.upper()} {path}: {parameter.get('name')} {schema}")
    return problems


def path_parameter_count(document: Document) -> int:
    return sum(
        1
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "path"
    )


def test_adr0005_c13_every_path_parameter_is_a_uuid() -> None:
    document = real_app().openapi()
    assert path_parameter_count(document) >= 1, "no path parameter: the check would be vacuous"
    assert path_parameter_problems(document) == []


def test_adr0005_c13_contrast_a_name_in_the_path_fails() -> None:
    document = {
        "paths": {
            "/api/customers/{name}": {
                "get": {
                    "parameters": [{"in": "path", "name": "name", "schema": {"type": "string"}}]
                }
            }
        }
    }
    assert path_parameter_problems(document) != []
