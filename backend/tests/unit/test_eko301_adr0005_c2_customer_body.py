"""EKO-3-01, ADR-0005-C2 on the first product endpoint that accepts a body: a create request
that fails validation and carries a marker in every field leaves the marker in no line the
backend logs.

The access dependency answers before the body is decoded (ADR-0003 addendum of EKO-3-01,
section 4), so the request must come from a caller that holds `rep`: the dependency is overridden
to that caller here, on the shipped `create_app()`, and the walk covers every body route.
Contrast: without the override the same requests never reach validation.
"""

from fastapi import FastAPI

from app.auth.gate import authenticate
from app.domain.caller import Caller, Role
from app.main import create_app
from tests.support.c2_routes import body_routes
from tests.unit.test_adr0005_c2_validation_input_not_logged import Output, c2_problems, output

__all__ = ["output"]

REP = Caller(subject="5a1e0301-0000-4000-8000-0000000000c2", name=None, roles=frozenset({Role.REP}))


def as_rep() -> Caller:
    return REP


def rep_app() -> FastAPI:
    app = create_app()
    app.dependency_overrides[authenticate] = as_rep
    return app


def test_adr0005_c2_customer_create_validation_input_not_logged(
    backend_env: None, output: Output
) -> None:
    app = rep_app()
    routes = body_routes(app)
    assert ("POST", "/api/customers") in {(r.method, r.path) for r in routes}
    assert c2_problems(app, routes, output) == []


def test_adr0005_c2_contrast_without_a_caller_validation_is_not_reached(
    backend_env: None, output: Output
) -> None:
    app = create_app()
    problems = c2_problems(app, body_routes(app), output)
    assert any("status 403" in p for p in problems), problems
    assert not any("the rejected input is in the log" in p for p in problems), problems
