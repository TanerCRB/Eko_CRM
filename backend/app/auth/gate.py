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
"""

from typing import Annotated

from fastapi import Depends, Request

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


def authenticate(request: Request) -> Caller | None:
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
