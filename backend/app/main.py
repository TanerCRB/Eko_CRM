"""Application factory: `uvicorn app.main:create_app --factory`.

The request half of ADR-0005's addendum of 2026-11-02 lives here, where ADR-0001 places error
handling: `install_request_handling` puts one ASGI layer outside Starlette's server-error
middleware. It binds a correlation identifier per request, adds `Eko-Correlation-Id` to every
response and `Cache-Control: no-store` under `/api/`, writes the request line, and writes the
error line of an unhandled exception once, as its type and location only.
"""

import logging
import re
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, routing
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.auth.crypto import Sealer
from app.auth.gate import OriginRefused, authenticate
from app.auth.oidc import OidcClient, http_client
from app.auth.sessions import Authenticator, Unauthenticated, Unavailable
from app.core.clock import SystemClock
from app.core.logs import RequestLine, correlation_id, install_interpreter_hooks
from app.core.settings import AuthSettings, Settings, load_settings
from app.data.database import Database
from app.data.sessions import SessionStore, StorageUnavailable

logger = logging.getLogger(__name__)

# The access dependency's exemption list (ADR-0003 addendum of 2026-10-28): exactly these three.
# Adding a path here is a change to ADR-0003, recorded as an addendum.
PUBLIC_PATHS = frozenset({"/api/auth/login", "/api/auth/callback", "/api/health"})

STANDARD_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}
)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
ROUTE_LIMIT = 256
CORRELATION_HEADER = b"eko-correlation-id"
SERVER_ERROR_BODY = b"Internal Server Error"


def _is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def opaque_route(path: str, fixed_segments: frozenset[str]) -> str:
    """An unmatched path with every segment that is not a fixed route segment or a lower-case
    UUID written `*`, so no value a client put in the path is written."""
    segments = path.split("/")
    kept = [s if s == "" or s in fixed_segments or UUID.fullmatch(s) else "*" for s in segments]
    return "/".join(kept)[:ROUTE_LIMIT]


class RequestHandling:
    """The outermost layer: outside Starlette's server-error middleware, so it also shapes the
    500 that middleware sends and the router's own 404, 405 and redirects."""

    def __init__(self, app: ASGIApp, served: FastAPI) -> None:
        self.app = app
        self.served = served

    def _route(self, scope: Scope) -> str:
        # Read from the routes as served: an included router is one entry of `app.routes`, and
        # the matched route's own path lacks the router's prefix.
        contexts = list(routing.iter_route_contexts(self.served.routes))
        matched = scope.get("route")
        for context in contexts:
            if matched is not None and context.route is matched:
                return (context.path or "")[:ROUTE_LIMIT]
        fixed = frozenset(
            segment
            for context in contexts
            for segment in (context.path or "").split("/")
            if segment and "{" not in segment
        )
        return opaque_route(str(scope.get("path", "")), fixed)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        identifier = secrets.token_hex(16)
        bound = correlation_id.set(identifier)
        started = time.perf_counter_ns()
        api = _is_api(str(scope.get("path", "")))
        status: int | None = None

        async def shaped(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                dropped = {CORRELATION_HEADER, b"cache-control"} if api else {CORRELATION_HEADER}
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in dropped
                ]
                headers.append((CORRELATION_HEADER, identifier.encode("ascii")))
                if api:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, shaped)
        except Exception:
            # Written once, here; the exception is not passed on, so uvicorn writes no second one.
            logger.error("unhandled exception in a request", exc_info=True)
            if status is None:
                await shaped(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(SERVER_ERROR_BODY)).encode("ascii")),
                        ],
                    }
                )
                await shaped({"type": "http.response.body", "body": SERVER_ERROR_BODY})
        finally:
            method = str(scope.get("method", ""))
            line = RequestLine(
                method=method if method in STANDARD_METHODS else "OTHER",
                route=self._route(scope),
                status=500 if status is None else status,
                duration_ms=round((time.perf_counter_ns() - started) / 1_000_000, 3),
                correlation_id=identifier,
            )
            logger.info("request", extra={"eko_request": line})
            correlation_id.reset(bound)


async def _rejected_request(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return await request_validation_exception_handler(request, exc)


async def _http_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, HTTPException):
        raise exc
    return await http_exception_handler(request, exc)


def install_request_handling(app: FastAPI) -> None:
    """The one entry for the request half; `create_app()` and every fixture app call it."""
    if app.middleware_stack is not None:
        raise RuntimeError("request handling must be installed before the first request")
    # FastAPI's own handlers, named so a fixture app gets the same ones: none writes a message
    # or the rejected input to a log.
    app.add_exception_handler(RequestValidationError, _rejected_request)
    app.add_exception_handler(HTTPException, _http_error)
    inner = app.build_middleware_stack

    def build() -> ASGIApp:
        return RequestHandling(inner(), app)

    # The only hook outside Starlette's ServerErrorMiddleware, which build_middleware_stack puts
    # outermost; a user middleware would sit inside it and miss its 500.
    app.build_middleware_stack = build  # type: ignore[method-assign]


def _problem(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


async def _unauthenticated(request: Request, exc: Exception) -> Response:
    return _problem(401, "not authenticated")


async def _origin_refused(request: Request, exc: Exception) -> Response:
    return _problem(403, "origin refused")


async def _unavailable(request: Request, exc: Exception) -> Response:
    return _problem(503, "temporarily unavailable")


def _public_routes(app: FastAPI) -> tuple[object, ...]:
    """The served route objects of `PUBLIC_PATHS`; building fails unless each path is found."""
    found = [c for c in routing.iter_route_contexts(app.routes) if c.path in PUBLIC_PATHS]
    if {c.path for c in found} != PUBLIC_PATHS:
        raise RuntimeError("a public route is not served")
    return tuple(c.route for c in found)


def create_app() -> FastAPI:
    # Uvicorn's worker processes are fresh interpreters that apply only `log_config`; this is the
    # one place a serving process gets the hooks (ADR-0005 amendment at verification, R-01).
    install_interpreter_hooks()
    try:
        settings = load_settings(Settings)
        auth_settings = load_settings(AuthSettings)
        database = Database.from_settings(settings)
        http = http_client()
        auth = Authenticator(
            origin=auth_settings.app_origin,
            store=SessionStore(database),
            oidc=OidcClient(auth_settings, http),
            sealer=Sealer(auth_settings.session_key()),
            clock=SystemClock(),
        )

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            yield
            http.close()
            database.dispose()

        # The OpenAPI document and docs stay outside /api/: proxy forwards only /api/ to backend,
        # so they are reachable only inside the composition network (ADR-0003-C23).
        app = FastAPI(
            title="Eko_CRM API",
            openapi_url="/openapi.json",
            docs_url="/docs",
            redoc_url="/redoc",
            lifespan=lifespan,
            # Every route, one registered later included, passes the access dependency.
            dependencies=[Depends(authenticate)],
        )
        app.state.database = database
        app.state.auth = auth
        app.include_router(health_router, prefix="/api")
        app.include_router(auth_router, prefix="/api")
        auth.public_routes = _public_routes(app)
        app.add_exception_handler(Unauthenticated, _unauthenticated)
        app.add_exception_handler(OriginRefused, _origin_refused)
        app.add_exception_handler(Unavailable, _unavailable)
        app.add_exception_handler(StorageUnavailable, _unavailable)
        install_request_handling(app)
        return app
    except Exception:
        # Uvicorn catches only a TypeError from the factory; anything else would reach
        # multiprocessing's traceback print with its message (ADR-0005 amendment, S-2).
        logger.error("the application could not be built", exc_info=True)
        raise SystemExit(1) from None
