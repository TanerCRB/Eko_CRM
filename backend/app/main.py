"""Application factory: `uvicorn app.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.settings import Settings, load_settings
from app.data.database import Database


def create_app() -> FastAPI:
    settings = load_settings(Settings)
    database = Database.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        database.dispose()

    # The OpenAPI document and docs stay outside /api/: proxy forwards only /api/ to backend, so
    # they are reachable only inside the composition network (ADR-0003-C23).
    app = FastAPI(
        title="Eko_CRM API",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.database = database
    app.include_router(health_router, prefix="/api")
    return app
