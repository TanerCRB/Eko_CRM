"""EKO-3-01, ADR-0003-C34 (the mechanism's own guard): the application refuses to serve a route
that would read its body before the access decision. A router created without
`AccessFirstRoute` and included after `create_app()` makes building the middleware stack, which
happens before the first request, fail; the same router with the class builds.
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.auth.gate import AccessFirstRoute, routes_without_access_first
from app.main import create_app


class Body(BaseModel):
    name: str


class Out(BaseModel):
    ok: bool


def with_router(route_class: type[APIRoute]) -> FastAPI:
    app = create_app()
    router = APIRouter(route_class=route_class)

    @router.post("/api/eko301-planted")
    def planted(body: Body) -> Out:
        return Out(ok=True)

    app.include_router(router)
    return app


def test_c34_every_shipped_route_is_access_first(backend_env: None) -> None:
    assert routes_without_access_first(create_app()) == []


def test_c34_a_router_without_the_class_is_never_served(backend_env: None) -> None:
    app = with_router(APIRoute)
    assert routes_without_access_first(app) == ["/api/eko301-planted"]
    with pytest.raises(RuntimeError, match="before the access decision"):
        app.build_middleware_stack()


def test_c34_contrast_the_same_router_with_the_class_builds(backend_env: None) -> None:
    app = with_router(AccessFirstRoute)
    assert routes_without_access_first(app) == []
    app.build_middleware_stack()
