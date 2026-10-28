"""The health route: one of the three routes served without a session (ADR-0003-C23)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from app.data.database import Database
from app.services.health import is_ready

router = APIRouter()


class HealthStatus(BaseModel):
    # Status only: no version, revision, host, dependency name or error text.
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable"]


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


_RESPONSES: dict[int | str, dict[str, object]] = {503: {"model": HealthStatus}}


# Two registrations, not one api_route: a shared operationId makes the OpenAPI document invalid.
@router.get("/health", response_model=HealthStatus, responses=_RESPONSES, operation_id="health")
@router.head(
    "/health", response_model=HealthStatus, responses=_RESPONSES, operation_id="health_head"
)
def health(
    response: Response, database: Annotated[Database, Depends(get_database)]
) -> HealthStatus:
    if is_ready(database):
        return HealthStatus(status="ok")
    response.status_code = 503
    return HealthStatus(status="unavailable")
