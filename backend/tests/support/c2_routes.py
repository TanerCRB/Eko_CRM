"""ADR-0005-C2: every route that accepts a body, and invalid requests carrying a marker in each
field. Read from the route table as served (`api_surface.route_contexts`), dependencies included,
so an included router or a body read by a dependency is not missed."""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from tests.support.api_surface import route_contexts


@dataclass(frozen=True)
class BodyRoute:
    method: str
    path: str
    fields: tuple[str, ...]


def _body_fields(route: APIRoute) -> list[Any]:
    stack, found = [route.dependant], []
    while stack:
        dependant = stack.pop()
        stack += dependant.dependencies
        found += list(dependant.body_params)
    return found


def body_routes(app: FastAPI) -> list[BodyRoute]:
    routes = []
    for context in route_contexts(app):
        if not isinstance(context.route, APIRoute):
            continue
        fields = _body_fields(context.route)
        if not fields:
            continue
        names: list[str] = []
        for field in fields:
            model = getattr(field.field_info, "annotation", None)
            if isinstance(model, type) and issubclass(model, BaseModel):
                names += list(model.model_fields)
            else:
                names.append(str(field.alias))
        for method in sorted(context.methods or set()):
            routes.append(BodyRoute(method, context.path or "", tuple(names)))
    return routes


def invalid_bodies(route: BodyRoute, marker: str) -> dict[str, dict[str, Any]]:
    """Request variants (httpx keyword arguments) that fail validation, each carrying the marker."""
    wrong_type = {name: {"value": marker, "nested": [marker]} for name in route.fields}
    return {
        "every-field-wrong-type": {"json": wrong_type},
        "every-field-a-marker-string-plus-unknown": {
            "json": {**{name: marker for name in route.fields}, f"unknown_{marker[:8]}": marker}
        },
        "not-json": {
            "content": f'{{"{marker}": "{marker}"'.encode(),
            "headers": {"content-type": "application/json"},
        },
        "form": {"data": {name: marker for name in route.fields}},
        "wrong-content-type": {
            "content": marker.encode(),
            "headers": {"content-type": "text/plain"},
        },
        "absent": {},
    }
