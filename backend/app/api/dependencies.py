"""Request-scoped dependencies shared by the API's routers."""

from fastapi import Request

from app.core.clock import Clock
from app.data.database import Database


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


def get_clock(request: Request) -> Clock:
    """The application's one clock (ADR-0002-C13), set by `create_app()`; a test sets its own."""
    clock: Clock = request.app.state.clock
    return clock
