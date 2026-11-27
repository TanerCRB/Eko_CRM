"""Visits: plan, read by identifier, list all or a period (EKO-4-01; VIS-1 app side, VIS-3 location
rule, ACC-4, ACC-5, ACC-7, PRH-4; the accepted addendum's ADR-0003-C42).

The handlers pass the caller value inward and decide nothing about ownership. A wall time crosses
as a Europe/Warsaw local date `YYYY-MM-DD` and a local time `HH:MM`, with no offset and no zone
(ADR-0001 Constraint 3), and is resolved to an instant by `app.domain.warsaw` while the body is
judged: a time the clocks skip or repeat is a 422 whose `type` names the reason at its field,
`start` or `end` (ADR-0002-C15). Instants are answered with their offset (UTC). A period is two
Warsaw dates in the query, never a path segment (ADR-0005-C13); the visit identifier, a UUID, is
the only path parameter. A visit's state is derived by the service from the injected clock.

A visit outside the caller's scope is answered exactly as one that exists nowhere: 404 `not
found`; so is a customer outside the caller's own records, but for an all-records caller that can
read it (403 `not permitted`, gate 1 A-2 A). An own archived customer is 409 `restore it first`.
No answer names a visit's owner. Every response here carries `Cache-Control: no-store`, set for
all of `/api/` in `main.py` (ADR-0005-C12).
"""

import re
from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.api.auth import Problem
from app.api.customers import RequestModel, customer_store
from app.api.dependencies import get_clock, get_database
from app.auth.gate import AccessFirstRoute, current_caller
from app.core.clock import Clock
from app.data.customers import CustomerStore
from app.data.database import Database
from app.data.visits import VisitStore
from app.domain import visits as rules
from app.domain import warsaw
from app.domain.caller import Caller
from app.domain.visits import ShownVisit, VisitDraft
from app.services import visits as service

router = APIRouter(prefix="/visits", route_class=AccessFirstRoute)

# Exactly two digits each, a 24-hour clock; no seconds, offset or zone.
WALL_CLOCK = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
CALENDAR_DAY = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
CALENDAR_DATE = re.compile(CALENDAR_DAY)
# The machine value of each refusal of ADR-0002-C15, as the 422's `type`.
REASON_TYPES = {
    warsaw.WallTimeReason.NONEXISTENT: "nonexistent_local_time",
    warsaw.WallTimeReason.AMBIGUOUS: "ambiguous_local_time",
}


class WallTimeIn(RequestModel):
    """A Europe/Warsaw wall time as typed: a calendar date and an `HH:MM` time."""

    # Exactly `YYYY-MM-DD`, never an instant, a timestamp or a number; a string, since the body
    # is judged after JSON decoding, where a strict `date` would refuse every string.
    date: Annotated[
        StrictStr, Field(max_length=10, pattern=CALENDAR_DAY, json_schema_extra={"format": "date"})
    ]
    time: Annotated[StrictStr, Field(max_length=5, pattern=WALL_CLOCK)]
    _instant: datetime = PrivateAttr()

    @field_validator("date")
    @classmethod
    def _calendar_day(cls, value: str) -> str:
        _calendar_date(value)
        return value

    @model_validator(mode="after")
    def _resolved(self) -> "WallTimeIn":
        day = Date.fromisoformat(self.date)
        try:
            self._instant = warsaw.instant_of(day, Time.fromisoformat(self.time))
        except warsaw.WallTimeRefused as refused:
            # The message is fixed per reason and repeats no typed value.
            raise PydanticCustomError(REASON_TYPES[refused.reason], str(refused)) from None
        return self

    @property
    def instant(self) -> datetime:
        return self._instant


class VisitCreate(RequestModel):
    """A visit to plan. The owner is never part of the request: an unknown field is a 422. The
    own address is optional; omitted, `null`, `""` or whitespace only is not given (K-03)."""

    customer_id: UUID
    start: WallTimeIn
    # Declared after `start`: a validator sees only the fields before it.
    end: WallTimeIn
    own_address: Annotated[StrictStr, Field(max_length=rules.OWN_ADDRESS_RAW_LIMIT)] | None = None

    @field_validator("end")
    @classmethod
    def _after_the_start(cls, end: WallTimeIn, info: ValidationInfo) -> WallTimeIn:
        # Without a valid start the request is already refused for it; the end is not compared.
        start = info.data.get("start")
        if isinstance(start, WallTimeIn):
            rules.check_end_after_start(start.instant, end.instant)
        return end

    @field_validator("own_address")
    @classmethod
    def _own_address(cls, value: str | None) -> str | None:
        return rules.own_address(value)

    def draft(self) -> VisitDraft:
        return VisitDraft(self.customer_id, self.start.instant, self.end.instant, self.own_address)


# The largest create body whose every field passes its raw cap: each code point of a value or a
# key at most 12 bytes (an astral character written as two `\uXXXX` escapes), plus the braces,
# quotes and separators, generously. The identifier is counted at its longest accepted form.
_ESCAPED_BYTES_PER_CODE_POINT = 12
_OBJECT_FRAMING = 256
_KEYS = ("customer_id", "start", "end", "own_address", *2 * ("date", "time"))
_UUID_TEXT = len("urn:uuid:") + 36
_WALL_TIME_TEXT = len("2026-11-30") + len("10:00")
LARGEST_VISIT_BODY = _OBJECT_FRAMING + _ESCAPED_BYTES_PER_CODE_POINT * (
    sum(len(key) for key in _KEYS) + rules.OWN_ADDRESS_RAW_LIMIT + _UUID_TEXT + 2 * _WALL_TIME_TEXT
)


class VisitCustomerOut(BaseModel):
    """The customer a visit is for: its identifier, name and current address, every address part
    `null` when not given (ADR-0003-C42; read under the visit's scope, A-3 A)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    street: str | None
    postal_code: str | None
    town: str | None
    voivodeship: str | None
    county: str | None


class VisitOut(BaseModel):
    """A visit as stored, with its state at the moment of the answer. `own_address` is the
    visit's own address, shown instead of the customer's when it is not `null` (VIS-3, G-8 A).
    `state` is derived from `ends_at` and the server's clock, never stored."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    customer: VisitCustomerOut
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    own_address: str | None
    state: Literal["planned", "held"]

    @classmethod
    def of(cls, shown: ShownVisit) -> "VisitOut":
        visit, customer = shown.visit, shown.visit.customer
        address = customer.address
        return cls(
            id=visit.id,
            customer=VisitCustomerOut(
                id=customer.id,
                name=customer.name,
                street=address.street,
                postal_code=address.postal_code,
                town=address.town,
                voivodeship=address.voivodeship,
                county=address.county,
            ),
            starts_at=visit.starts_at,
            ends_at=visit.ends_at,
            own_address=visit.own_address,
            state=shown.state.value,
        )


class VisitList(BaseModel):
    """The caller's visible visits in start order (the order among equal starts is not part of
    the contract), with no paging (Out of scope) and no count or other field."""

    model_config = ConfigDict(extra="forbid")

    items: list[VisitOut]

    @classmethod
    def of(cls, shown: list[ShownVisit]) -> "VisitList":
        return cls(items=[VisitOut.of(visit) for visit in shown])


_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem},
    403: {"model": Problem},
    503: {"model": Problem},
}


def visit_store(database: Annotated[Database, Depends(get_database)]) -> VisitStore:
    return VisitStore(database)


Store = Annotated[VisitStore, Depends(visit_store)]
Customers = Annotated[CustomerStore, Depends(customer_store)]
CurrentCaller = Annotated[Caller, Depends(current_caller)]
CurrentClock = Annotated[Clock, Depends(get_clock)]


def _calendar_date(raw: str) -> Date:
    """A Gregorian date written exactly `YYYY-MM-DD`; `date.fromisoformat` alone also takes
    other ISO 8601 forms, such as `20261130`."""
    if not CALENDAR_DATE.fullmatch(raw):
        raise ValueError("not a calendar date (YYYY-MM-DD)")
    try:
        return Date.fromisoformat(raw)
    except ValueError:
        raise ValueError("not a calendar date (YYYY-MM-DD)") from None


def _refused(name: str, message: str) -> dict[str, Any]:
    # A fixed message: the value itself is never repeated (ADR-0005).
    return {
        "type": "value_error",
        "loc": ("query", name),
        "msg": f"Value error, {message}",
        "ctx": {"error": message},
    }


def visit_period(
    first: Annotated[
        str,
        Query(
            description="The period's first Europe/Warsaw calendar date, YYYY-MM-DD.",
            json_schema_extra={"format": "date"},
        ),
    ],
    last: Annotated[
        str,
        Query(
            description="The period's last Europe/Warsaw calendar date, YYYY-MM-DD, included.",
            json_schema_extra={"format": "date"},
        ),
    ],
) -> warsaw.Period:
    """The period's two dates, judged before any service runs; a refusal is a 422 naming the
    parameter and repeating no value. A day is `first` = `last`."""
    errors: list[dict[str, Any]] = []
    dates: dict[str, Date] = {}
    for name, raw in (("first", first), ("last", last)):
        try:
            dates[name] = _calendar_date(raw)
        except ValueError as exc:
            errors.append(_refused(name, str(exc)))
    if errors:
        raise RequestValidationError(errors)
    try:
        return warsaw.period_of(dates["first"], dates["last"])
    except warsaw.PeriodRefused as refused:
        raise RequestValidationError([_refused(refused.bound, str(refused))]) from None


Period = Annotated[warsaw.Period, Depends(visit_period)]


@router.post(
    "",
    operation_id="visit_create",
    status_code=201,
    response_model=VisitOut,
    # 404: the customer is not the caller's own or exists nowhere; 403 also for an all-records
    # caller naming a customer it does not own; 409 `restore it first`: an own archived customer.
    responses={**_REFUSALS, 404: {"model": Problem}, 409: {"model": Problem}},
)
def create_visit(
    body: VisitCreate,
    caller: CurrentCaller,
    store: Store,
    customers: Customers,
    clock: CurrentClock,
) -> VisitOut:
    return VisitOut.of(service.plan_visit(store, customers, caller, body.draft(), clock))


@router.get("", operation_id="visit_list", response_model=VisitList, responses=_REFUSALS)
def list_visits(caller: CurrentCaller, store: Store, clock: CurrentClock) -> VisitList:
    """Every visit the caller may read, past and future."""
    return VisitList.of(service.list_visits(store, caller, None, clock))


@router.get(
    "/period",
    operation_id="visit_period",
    response_model=VisitList,
    responses=_REFUSALS,
)
def list_period(
    caller: CurrentCaller, store: Store, clock: CurrentClock, period: Period
) -> VisitList:
    """The visits the caller may read whose start falls in the period's Warsaw days."""
    return VisitList.of(service.list_visits(store, caller, period, clock))


@router.get(
    "/{visit_id}",
    operation_id="visit_read",
    response_model=VisitOut,
    responses={**_REFUSALS, 404: {"model": Problem}},
)
def read_visit(
    visit_id: UUID, caller: CurrentCaller, store: Store, clock: CurrentClock
) -> VisitOut:
    return VisitOut.of(service.read_visit(store, caller, visit_id, clock))
