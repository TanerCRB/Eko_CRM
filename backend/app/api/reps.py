"""The manager's list of reps (EKO-3-08; G-4 A: a staff route outside `/api/customers`, for the
owner selector and EKO-3-07's reassignment).

A CRM-class operation, unmarked in `main.py`'s lists, so an administrator-only or role-less caller
is refused by the app-wide gate; the gate admits a rep, so the route's own manager check is the
only guard for a rep (ADR-0003-C5). It takes no parameter, so it has no 422 that could repeat a
value. Each entry is the subject and the display name only (ADR-0005 PD-S3); the response carries
`Cache-Control: no-store`, set for all of `/api/` in `main.py`.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.auth import Problem
from app.api.dependencies import get_database
from app.auth.gate import AccessFirstRoute, manager_caller
from app.data.database import Database
from app.data.staff import StaffStore
from app.domain.caller import Caller
from app.domain.staff import Rep
from app.services import staff as service

router = APIRouter(prefix="/reps", route_class=AccessFirstRoute)


class RepEntry(BaseModel):
    """A rep: the subject and the display name copied at its last login, `null` when none."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    name: str | None

    @classmethod
    def of(cls, rep: Rep) -> "RepEntry":
        return cls(subject=rep.subject, name=rep.name)


class RepList(BaseModel):
    """The reps, with no sort order guaranteed (G-6 A) and no paging; no count or other field."""

    model_config = ConfigDict(extra="forbid")

    items: list[RepEntry]


_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem},
    403: {"model": Problem},
    503: {"model": Problem},
}


def staff_store(database: Annotated[Database, Depends(get_database)]) -> StaffStore:
    return StaffStore(database)


@router.get("", operation_id="rep_list", response_model=RepList, responses=_REFUSALS)
def list_reps(
    caller: Annotated[Caller, Depends(manager_caller)],
    store: Annotated[StaffStore, Depends(staff_store)],
) -> RepList:
    """Staff whose last login's token held `rep`."""
    return RepList(items=[RepEntry.of(rep) for rep in service.list_reps(store)])
