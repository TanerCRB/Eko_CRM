"""Reference data the SPA picks from (EKO-3-02, Q-3 A): the voivodeships and counties of the
dated TERYT file, served from the same `app.domain.regions` the create rule validates with, so
the form's lists and the server's rule have one source.

A CRM operation like any other not on the ADR-0003 lists: it needs a session and an application
role. It reads no table and holds no personal data.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.auth import Problem
from app.auth.gate import AccessFirstRoute, crm_data_caller
from app.domain import regions

router = APIRouter(prefix="/reference", route_class=AccessFirstRoute)


class VoivodeshipOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # The county names of this voivodeship, in the register's order.
    counties: list[str]


class VoivodeshipList(BaseModel):
    """Every voivodeship in the register's order, with the register's date (`as_of`)."""

    model_config = ConfigDict(extra="forbid")

    as_of: date
    voivodeships: list[VoivodeshipOut]


_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem},
    403: {"model": Problem},
    503: {"model": Problem},
}


@router.get(
    "/voivodeships",
    operation_id="voivodeship_list",
    response_model=VoivodeshipList,
    responses=_REFUSALS,
    dependencies=[Depends(crm_data_caller)],
)
def list_voivodeships() -> VoivodeshipList:
    return VoivodeshipList(
        as_of=regions.REGISTER.as_of,
        voivodeships=[
            VoivodeshipOut(name=v.name, counties=[c.name for c in v.counties])
            for v in regions.REGISTER.voivodeships
        ],
    )
