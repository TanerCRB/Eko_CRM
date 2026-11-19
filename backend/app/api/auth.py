"""Login start, login callback, session and logout (ADR-0003 *Browser flow*; G-2 A).

Login start and the callback are two of the three routes served without a session; the session
and logout operations go through the access dependency like every other route. Both are non-CRM
operations, so an administrator-only caller reaches them; logout alone is role-free, so a caller
with no application role can still end its session (ADR-0003 roles addendum of EKO-2-02; the
lists are `main.py`'s). No body or readable cookie carries a token: the browser gets only the
opaque session and login-transaction identifiers, in `HttpOnly` `__Host-` cookies.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from app.auth.gate import (
    LOGIN_COOKIE,
    SESSION_COOKIE,
    AccessFirstRoute,
    authenticator,
    current_caller,
)
from app.auth.sessions import LoginRefused, Unavailable
from app.data.sessions import StorageUnavailable
from app.domain.caller import Caller
from app.domain.session_policy import ABSOLUTE_LIMIT, LOGIN_TRANSACTION_VALIDITY

router = APIRouter(prefix="/auth", route_class=AccessFirstRoute)

LOGIN_TRANSACTION_MAX_AGE = int(LOGIN_TRANSACTION_VALIDITY.total_seconds())
SESSION_MAX_AGE = int(ABSOLUTE_LIMIT.total_seconds())


class Redirect(BaseModel):
    """The body of a 303: the same target as its `Location` header."""

    model_config = ConfigDict(extra="forbid")

    location: str


class SessionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    name: str | None


class LoggedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["logged_out"]


class Problem(BaseModel):
    """The error body of every refusal: FastAPI's own shape."""

    detail: str


def _redirect(response: Response, location: str) -> Redirect:
    response.status_code = 303
    response.headers["location"] = location
    return Redirect(location=location)


def _clear(response: Response, name: str, samesite: Literal["lax", "strict"]) -> None:
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite=samesite)


# A refused or unavailable callback is a top-level navigation the SPA never sees, so it goes to
# the SPA's failure page instead of a JSON body (Reviewer R-03).
LOGIN_FAILED_PAGE = "/logowanie-nieudane"
_LOGIN_UNAVAILABLE: dict[int | str, dict[str, Any]] = {503: {"model": Problem}}
_UNAUTHENTICATED: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem},
    403: {"model": Problem},
    503: {"model": Problem},
}


@router.get(
    "/login",
    operation_id="login_start",
    status_code=303,
    response_model=Redirect,
    responses={
        303: {"model": Redirect, "description": "To the identity server's login page."},
        **_LOGIN_UNAVAILABLE,
    },
)
def login_start(request: Request, response: Response, return_to: str | None = None) -> Redirect:
    started = authenticator(request).start_login(return_to)
    response.set_cookie(
        LOGIN_COOKIE,
        started.transaction,
        max_age=LOGIN_TRANSACTION_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return _redirect(response, started.location)


@router.get(
    "/callback",
    operation_id="login_callback",
    status_code=303,
    response_model=Redirect,
    responses={
        303: {
            "model": Redirect,
            "description": (
                f"To the requested page; to {LOGIN_FAILED_PAGE} when the login was refused or "
                "could not be completed, with no session created."
            ),
        }
    },
)
def login_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Redirect:
    try:
        done = authenticator(request).finish_login(
            request.cookies.get(LOGIN_COOKIE),
            code,
            state,
            error,
            request.cookies.get(SESSION_COOKIE),
        )
    except (LoginRefused, Unavailable, StorageUnavailable):
        _clear(response, LOGIN_COOKIE, "lax")
        return _redirect(response, LOGIN_FAILED_PAGE)
    _clear(response, LOGIN_COOKIE, "lax")
    response.set_cookie(
        SESSION_COOKIE,
        done.session,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return _redirect(response, done.return_to)


@router.get(
    "/session", operation_id="session_read", response_model=SessionInfo, responses=_UNAUTHENTICATED
)
def session_read(caller: Annotated[Caller, Depends(current_caller)]) -> SessionInfo:
    return SessionInfo(subject=caller.subject, name=caller.name)


@router.post("/logout", operation_id="logout", response_model=LoggedOut, responses=_UNAUTHENTICATED)
def logout(
    request: Request, response: Response, caller: Annotated[Caller, Depends(current_caller)]
) -> LoggedOut:
    authenticator(request).logout(request.cookies.get(SESSION_COOKIE))
    _clear(response, SESSION_COOKIE, "strict")
    return LoggedOut(status="logged_out")
