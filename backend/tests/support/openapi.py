"""ADR-0001-C7: is a document a valid OpenAPI 3.x document? Shared by the unit and runtime tests."""

from typing import Any

from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError


def openapi_3_errors(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["not a JSON object"]
    version = document.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        return [f"not an OpenAPI 3.x document (openapi={version!r})"]
    try:
        validate(document)
    except OpenAPIValidationError as exc:
        return [str(exc).splitlines()[0]]
    return []
