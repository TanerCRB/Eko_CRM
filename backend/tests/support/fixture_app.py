"""Test-only routes on the shipped application, and the process logging around a unit test.

ADR-0005 addendum of 2026-11-02, *A fixture uses the same entries*: a fixture app is
`create_app()` with test-only routes added, so it carries the repository's request handling. No
route here ships: the change-set check compares `create_app()`'s route table with the base's.

The module imports nothing from `tests`, so the runtime fixture copies it unchanged into a test
variant image built `FROM` the shipped one, where `serve.main` loads one of its factories. Its
marker is therefore fixed, so the test process knows the value the container raises.
"""

import logging
import sys
import threading
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import anyio
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.types import ASGIApp, Receive, Scope, Send

# Synthetic, and fixed: the container and the test process must agree on it.
TOKEN = "e113f1x7"
MARKER = f"marker-{TOKEN}"
NON_ASCII_MARKER = f"Zażółć-{TOKEN}"
LONG_MARKER = f"long-{TOKEN}-" + "x" * 1200
# Synthetic connection values a driver message names: none may reach a log.
DRIVER_HOST = f"db-{TOKEN}.invalid"
DRIVER_ROLE = f"role_{TOKEN}"
DRIVER_SECRET = f"pw-{TOKEN}"
DRIVER_URL = f"postgresql+psycopg://{DRIVER_ROLE}:{DRIVER_SECRET}@{DRIVER_HOST}:5432/eko"
FORBIDDEN = (MARKER, NON_ASCII_MARKER, LONG_MARKER[:40], DRIVER_HOST, DRIVER_ROLE, DRIVER_SECRET)
FORBIDDEN_TEXT = ("[SQL", "[parameters", "Traceback", DRIVER_URL)

Fixture = Callable[[], FastAPI]


class Inner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str


class FixtureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    count: int
    inner: Inner


class Accepted(BaseModel):
    accepted: bool


def driver_error() -> IntegrityError:
    """SQLAlchemy's wrapper as the driver raises it: statement, parameters and a message naming
    the host, role and URL."""
    message = (
        f'duplicate key value violates unique constraint "t_v_key" DETAIL: Key (v)=({MARKER}) '
        f'already exists. connection to server at "{DRIVER_HOST}", user "{DRIVER_ROLE}" '
        f"({DRIVER_URL})"
    )
    return IntegrityError("INSERT INTO t (v) VALUES (%(v)s)", {"v": MARKER}, Exception(message))


def _raise_with_marker() -> None:
    try:
        raise ValueError(f"inner {MARKER}", MARKER)
    except ValueError as inner:
        raise RuntimeError(f"outer {MARKER} {NON_ASCII_MARKER}", MARKER) from inner


class RaisingFinalizer:
    def __del__(self) -> None:
        raise RuntimeError(f"finalizer {MARKER} {DRIVER_HOST} {DRIVER_ROLE}")


class RaisingMiddleware:
    """A middleware that raises for one path: a 500 from outside every route."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/api/fixture/middleware-boom":
            raise RuntimeError(f"middleware {MARKER}")
        await self.app(scope, receive, send)


def add_fixture_routes(app: FastAPI) -> FastAPI:
    log = logging.getLogger("app.fixture")

    @app.get("/api/fixture/boom")
    def boom() -> Accepted:
        _raise_with_marker()
        return Accepted(accepted=True)

    @app.get("/api/fixture/driver")
    def driver() -> Accepted:
        try:
            raise driver_error()
        except IntegrityError as error:
            raise OperationalError("SELECT 1", {"p": MARKER}, Exception(str(error))) from error

    @app.get("/api/fixture/real-driver")
    def real_driver(request: Request) -> Accepted:
        """A real driver error: the marker as a bound parameter the server cannot cast."""
        engine = request.app.state.database._engine
        with engine.connect() as connection:
            connection.execute(text("SELECT CAST(:v AS integer)"), {"v": MARKER})
        return Accepted(accepted=True)

    @app.get("/api/fixture/group")
    async def group() -> Accepted:
        async def fail() -> None:
            raise RuntimeError(f"in a task {MARKER}")

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(fail)
        return Accepted(accepted=True)

    @app.get("/api/fixture/long")
    def long() -> Accepted:
        raise RuntimeError(LONG_MARKER)

    @app.get("/api/fixture/pool")
    def pool() -> Accepted:
        try:
            raise driver_error()
        except IntegrityError:
            # As SQLAlchemy's pool logs an invalidated connection: its own logger, with exc_info.
            logging.getLogger("sqlalchemy.pool.impl.QueuePool").error(
                "Exception during reset or similar", exc_info=True
            )
        return Accepted(accepted=True)

    @app.get("/api/fixture/warn")
    def warn() -> Accepted:
        """As a serializer warning carrying an input value (Reviewer R-01)."""
        warnings.warn(f"serialized value may not be as expected [input_value={MARKER}]",
                      UserWarning, stacklevel=1)  # fmt: skip
        return Accepted(accepted=True)

    @app.get("/api/fixture/unraisable")
    def unraisable() -> Accepted:
        """A finalizer that raises, as a driver object's cleanup naming host and role."""
        doomed = RaisingFinalizer()
        del doomed
        return Accepted(accepted=True)

    @app.get("/api/fixture/thread-error")
    def thread_error() -> Accepted:
        def fail() -> None:
            raise RuntimeError(f"in a thread {MARKER} {DRIVER_URL}")

        worker = threading.Thread(target=fail)
        worker.start()
        worker.join()
        return Accepted(accepted=True)

    @app.get("/api/fixture/log-sync")
    def log_sync() -> Accepted:
        log.info("fixture line from a thread")
        return Accepted(accepted=True)

    @app.get("/api/fixture/log-async")
    async def log_async() -> Accepted:
        log.info("fixture line before the pause")
        await anyio.sleep(0.2)
        log.info("fixture line after the pause")
        return Accepted(accepted=True)

    @app.post("/api/fixture/body")
    def body(payload: FixtureBody) -> Accepted:
        return Accepted(accepted=True)

    @app.get("/api/fixture/cached")
    def cached() -> Response:
        return Response("cached", headers={"Cache-Control": "public, max-age=600"})

    app.add_middleware(RaisingMiddleware)
    bypass_access(app)
    return app


def _no_access_check() -> None:
    return None


def bypass_access(app: FastAPI) -> None:
    """The fixture app only: its routes carry the error-handling claims, not authentication
    (EKO-2-01, human decision H6-2 A on #21). `create_app()` itself sets no override."""
    from app.auth.gate import authenticate

    app.dependency_overrides[authenticate] = _no_access_check


@contextmanager
def restored_process_state() -> Iterator[None]:
    """Whatever a test installs into this process's logging and hooks is undone afterwards."""
    names = ["", "app", "uvicorn", "uvicorn.error", "uvicorn.access", "py.warnings"]
    loggers = [logging.getLogger(name) for name in names]
    saved = [(lg, lg.level, list(lg.handlers), lg.propagate, lg.disabled) for lg in loggers]
    hooks = (sys.excepthook, threading.excepthook, sys.unraisablehook, logging.raiseExceptions)
    printer = warnings.showwarning
    try:
        yield
    finally:
        logging.captureWarnings(False)
        for lg, level, handlers, propagate, disabled in saved:
            lg.setLevel(level)
            lg.handlers[:] = handlers
            lg.propagate = propagate
            lg.disabled = disabled
        sys.excepthook, threading.excepthook, sys.unraisablehook, logging.raiseExceptions = hooks
        warnings.showwarning = printer


def create() -> FastAPI:
    """The runtime fixture: the shipped factory with the test-only routes."""
    from app.main import create_app

    return add_fixture_routes(create_app())


def create_broken() -> FastAPI:
    """A failure inside `create_app()` in a uvicorn worker process (K-05 mutation 3)."""
    from app.data.database import Database
    from app.main import create_app

    def broken(settings: object) -> Database:
        raise RuntimeError(f"cannot build {MARKER} {DRIVER_URL}")

    Database.from_settings = broken  # type: ignore[method-assign]  # planted failure
    return create_app()


def create_type_error() -> FastAPI:
    """A factory failing with a TypeError: uvicorn's own factory-load record (K-05 mutation 6)."""
    raise TypeError(f"factory {MARKER} {DRIVER_URL}")


def bare() -> FastAPI:
    """Planted contrast: the fixture routes on an application without the request handling."""
    return add_fixture_routes(FastAPI())


def install_for_test(process: str) -> None:
    """The repository's `install_process_logging`, with its handler on the process's own
    standard error (fd 2), which `capfd` captures; pytest swaps `sys.stderr` between phases."""
    from app.core.logs import install_process_logging

    install_process_logging(process)
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and sys.__stderr__ is not None:
            handler.setStream(sys.__stderr__)
