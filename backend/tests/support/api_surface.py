"""The API surface the application declares: its OpenAPI document and its route table.

ADR-0001-C6 (OpenAPI half) and ADR-0003-C9 as restated 2026-10-29; checklist rule 9.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, routing
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.main import create_app

Document = dict[str, Any]

# Synthetic values only (ADR-0005): building the application reads its settings, and connects
# to nothing.
SYNTHETIC_SETTINGS = (
    ("APP_DB_PASSWORD", "synthetic-openapi-only"),
    ("APP_DB_POOL_SIZE", "1"),
    ("APP_DB_MAX_OVERFLOW", "0"),
)


@contextmanager
def synthetic_settings() -> Iterator[None]:
    saved = {name: os.environ.get(name) for name, _ in SYNTHETIC_SETTINGS}
    for name, value in SYNTHETIC_SETTINGS:
        os.environ.setdefault(name, value)
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def real_app() -> FastAPI:
    """The application `create_app()` builds, in-process: never through `proxy` (ADR-0003)."""
    with synthetic_settings():
        return create_app()


METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
SUBSCHEMAS = ("items", "additionalProperties", "not", "contains", "unevaluatedProperties")


def is_credential(name: str) -> bool:
    """ADR-0003-C9 (and ADR-0001-C6) as restated: any case, `password` anywhere in the name."""
    lowered = name.lower()
    return "password" in lowered or lowered in {"username", "grant_type"}


def resolve(document: Document, node: Any) -> Any:
    """Follows `$ref` chains to local components; a cycle stops at the first repeat."""
    seen: set[str] = set()
    while isinstance(node, dict) and isinstance(node.get("$ref"), str):
        ref = node["$ref"]
        if ref in seen or not ref.startswith("#/"):
            return {}
        seen.add(ref)
        target: Any = document
        for part in ref[2:].split("/"):
            target = target.get(part.replace("~1", "/").replace("~0", "~"), {})
        node = target
    return node


def schema_property_names(document: Document, schema: Any) -> list[str]:
    """Every property name at any depth of a schema, through `$ref`, combinators and items."""
    names: list[str] = []
    stack, seen = [schema], set()
    while stack:
        node = stack.pop()
        if isinstance(node, dict) and isinstance(node.get("$ref"), str):
            if node["$ref"] in seen:
                continue
            seen.add(node["$ref"])
        node = resolve(document, node)
        if not isinstance(node, dict):
            continue
        for name, sub in (node.get("properties") or {}).items():
            names.append(name)
            stack.append(sub)
        stack += [node[key] for key in SUBSCHEMAS if isinstance(node.get(key), dict)]
        for key in SUBSCHEMA_LISTS:
            stack += [sub for sub in node.get(key) or [] if isinstance(sub, dict)]
        stack += [sub for sub in (node.get("patternProperties") or {}).values()]
    return names


def operations(document: Document) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    found = []
    for path, item in (document.get("paths") or {}).items():
        item = resolve(document, item)
        for method in METHODS:
            if isinstance(item.get(method), dict):
                found.append((method.upper(), path, item, item[method]))
    return found


def credential_body_properties(document: Document) -> list[str]:
    """Request-body properties of any media type, at any depth, through `$ref`."""
    problems = []
    for method, path, _, operation in operations(document):
        body = resolve(document, operation.get("requestBody"))
        for media, content in ((body or {}).get("content") or {}).items():
            for name in schema_property_names(document, (content or {}).get("schema")):
                if is_credential(name):
                    problems.append(f"{method} {path}: {media} body property {name!r}")
    return problems


def credential_parameters(document: Document) -> list[str]:
    """Query, header, cookie and path parameters, at path or operation level, through `$ref`."""
    problems = []
    for method, path, item, operation in operations(document):
        for parameter in [*(item.get("parameters") or []), *(operation.get("parameters") or [])]:
            parameter = resolve(document, parameter)
            name = str(parameter.get("name", ""))
            if is_credential(name):
                problems.append(f"{method} {path}: {parameter.get('in')} parameter {name!r}")
    return problems


def _framework_paths(app: FastAPI) -> set[str]:
    """The document and docs FastAPI serves itself: not application operations."""
    return {
        p
        for p in (app.openapi_url, app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url)
        if p
    }


def _route_names(context: routing.RouteContext) -> list[str]:
    return [f"{method} {context.path}" for method in sorted(context.methods or {"-"})]


def route_contexts(app: FastAPI) -> list[routing.RouteContext]:
    """Every route as served, included routers flattened: what `app.openapi()` itself walks.

    `app.routes` holds an included router as one entry, so a walk over it alone judges nothing.
    """
    return list(routing.iter_route_contexts(app.routes))


def judged_routes(app: FastAPI) -> list[str]:
    return [
        name
        for context in route_contexts(app)
        if isinstance(context.route, APIRoute)
        for name in _route_names(context)
    ]


def route_response_problems(app: FastAPI) -> list[str]:
    """Checklist rule 9, response half: every route's response is a Pydantic model.

    FastAPI takes `response_model` from the return annotation unless one is given, and drops it
    for a `Response` subclass: so a bare `JSONResponse`, `dict` or `Any` is no model. Routes
    hidden from the schema are judged too.
    """
    problems = []
    framework = _framework_paths(app)
    for context in route_contexts(app):
        if isinstance(context.route, APIRoute):
            model = context.route.response_model
            if not (isinstance(model, type) and issubclass(model, BaseModel)):
                for name in _route_names(context):
                    problems.append(f"{name}: response {model!r} is not a Pydantic model")
        elif context.path not in framework:
            problems.append(f"{context.path!r}: not a FastAPI route with a model")
    return problems


INPUT_KINDS = ("query_params", "header_params", "cookie_params", "path_params", "body_params")


def _input_names(field: Any, kind: str) -> list[str]:
    names = [str(field.name), str(field.alias)]
    model = getattr(field.field_info, "annotation", None)
    if kind == "body_params" and isinstance(model, type) and issubclass(model, BaseModel):
        schema = model.model_json_schema()
        names += schema_property_names(schema, schema)
    return names


def credential_route_inputs(app: FastAPI) -> list[str]:
    """L-01: the same credential names, read from the route table rather than the document.

    A route hidden from the schema (`include_in_schema=False`) is invisible to the document
    checks; here every route's parameters, body fields and their models, and its dependencies'
    inputs are judged. A raw `await request.form()` read is not seen by either.
    """
    problems = []
    for context in route_contexts(app):
        if not isinstance(context.route, APIRoute):
            continue
        stack, found = [context.route.dependant], set()
        while stack:
            dependant = stack.pop()
            stack += dependant.dependencies
            for kind in INPUT_KINDS:
                for field in getattr(dependant, kind):
                    found |= {n for n in _input_names(field, kind) if is_credential(n)}
        problems += [f"{context.path}: credential-shaped input {name!r}" for name in sorted(found)]
    return problems
