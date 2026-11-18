"""The one application-wide access dependency (ADR-0001 Constraint 2, ADR-0003 *How a request is
verified*, *Roles* and addendum of 2026-10-28 on routes served without a session).

Installed on the application itself, so every route, including one registered later, passes
through it. In this order: it refuses a state-changing request whose `Origin` is not the
application's own; lets through the routes `main.py` names as public; resolves the session cookie;
admits the role-free routes; refuses a caller whose verified token holds none of the application's
roles; admits the non-CRM routes; and refuses every other route to a caller whose roles grant no
CRM data, so an administrator-only caller is refused by default (ADR-0003 roles addendum of
EKO-2-02). The route lists are the route objects `main.py` resolves when it builds the
application, read from the application's state and matched by identity. `crm_data_caller` repeats
the CRM check for routes that declare it; `manager_caller` is the manager check. A plain `def`:
the session lookup is synchronous database work (ADR-0002 addendum of 2026-10-28).

The decision is given before the request body is read (ADR-0003 addendum of EKO-3-01, section 4,
ADR-0003-C34): FastAPI decodes a JSON body before it solves any dependency, so every route is an
`AccessFirstRoute`, whose handler solves this dependency first and only then hands the request to
FastAPI's own. The decision is kept on the request, so the route's own solving reuses it instead
of resolving the session twice. `main.py` makes it the application's route class and refuses to
serve a route of any other class.
"""

from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response, routing
from fastapi.dependencies.utils import get_dependant, solve_dependencies
from fastapi.routing import APIRoute

from app.auth.sessions import Authenticator, Unauthenticated
from app.domain.caller import Caller

SESSION_COOKIE = "__Host-eko_session"
LOGIN_COOKIE = "__Host-eko_login"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class OriginRefused(Exception):
    """A state-changing request without the application's own `Origin`: HTTP 403."""


class RoleRefused(Exception):
    """An authenticated caller whose roles do not grant the operation: HTTP 403."""


def authenticator(request: Request) -> Authenticator:
    found: Authenticator = request.app.state.auth
    return found


# A request-scope key: the decision of this request, set only after the checks passed.
ACCESS_DECIDED = "eko.access_decided"


def authenticate(request: Request) -> Caller | None:
    if ACCESS_DECIDED in request.scope:
        decided: Caller | None = request.scope[ACCESS_DECIDED]
        return decided
    caller = _decide(request)
    request.scope[ACCESS_DECIDED] = caller
    return caller


def _decide(request: Request) -> Caller | None:
    auth = authenticator(request)
    if request.method not in SAFE_METHODS and request.headers.get("origin") != auth.origin:
        raise OriginRefused
    route = request.scope.get("route")
    if any(route is public for public in auth.public_routes):
        return None
    caller = auth.authenticate(request.cookies.get(SESSION_COOKIE))
    state = request.app.state
    if any(route is listed for listed in state.role_free_routes):
        return caller
    if not caller.has_any_role:
        raise RoleRefused
    if any(route is listed for listed in state.non_crm_routes):
        return caller
    if not caller.may_use_crm_data:
        raise RoleRefused
    return caller


def current_caller(caller: Annotated[Caller | None, Depends(authenticate)]) -> Caller:
    if caller is None:
        raise Unauthenticated
    return caller


def crm_data_caller(caller: Annotated[Caller, Depends(current_caller)]) -> Caller:
    if not caller.may_use_crm_data:
        raise RoleRefused
    return caller


def manager_caller(caller: Annotated[Caller, Depends(current_caller)]) -> Caller:
    if not caller.has_manager_rights:
        raise RoleRefused
    return caller


def _access(caller: Annotated[Caller | None, Depends(authenticate)]) -> None:
    """The access dependency alone; an override of `authenticate` applies here too."""


_ACCESS = get_dependant(path="", call=_access)

Handler = Callable[[Request], Coroutine[Any, Any, Response]]


class AccessFirstRoute(APIRoute):
    """A route whose access answer (401, 403, 503) never depends on its request body."""

    def get_route_handler(self) -> Handler:
        decoding = super().get_route_handler()

        async def access_first(request: Request) -> Response:
            async with AsyncExitStack() as stack:
                await solve_dependencies(
                    request=request,
                    dependant=_ACCESS,
                    dependency_overrides_provider=request.app,
                    async_exit_stack=stack,
                    embed_body_fields=False,
                )
            return await decoding(request)

        return access_first


def routes_without_access_first(app: FastAPI) -> list[str]:
    """The served API routes that would decode a body before the access decision."""
    return [
        context.path or ""
        for context in routing.iter_route_contexts(app.routes)
        if isinstance(context.route, APIRoute) and not isinstance(context.route, AccessFirstRoute)
    ]
