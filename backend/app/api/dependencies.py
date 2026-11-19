"""Request-scoped dependencies shared by the API's routers."""

from fastapi import Request

from app.data.database import Database


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database
