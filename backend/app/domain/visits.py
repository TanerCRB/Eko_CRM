"""Visits as the brief defines them (VIS-1 app side, VIS-3 location rule, glossary *Visit* and
*Visit states*) and the rules gate 1 of EKO-4-01 fixed (G-1 A to G-4 A, G-8 A; A-1 A, A-3 A, A-4 A).

A visit has exactly one customer and one owner, the rep that planned it. Its start and end are
instants, resolved from Europe/Warsaw wall times by `app.domain.warsaw`. Its state is derived from
the end instant and "now", never stored: Planned until the end, Held from the end on (P2
`stateOf`: `end <= now`). Its own address, when given, is shown instead of the customer's; it
holds no copy of a customer value, so the customer's current address shows through (G-8 A).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from uuid import UUID

from app.domain.customers import NFC_COMPOSITION_LIMIT, Address, given, stored_text

# K-03 (proposed bound, accepted at gate 1): counted on the trimmed NFC form.
OWN_ADDRESS_LIMIT = 200
OWN_ADDRESS_RAW_LIMIT = NFC_COMPOSITION_LIMIT * OWN_ADDRESS_LIMIT
END_NOT_AFTER_START = "the end is not after the start"


class VisitState(StrEnum):
    """The states this task reaches; Cancelled, Moved and Awaiting decision are EKO-4-02's and
    EKO-5's."""

    PLANNED = "planned"
    HELD = "held"


def state_at(ends_at: datetime, now: datetime) -> VisitState:
    """Held from the end instant itself on, Planned before it, a visit in progress included."""
    return VisitState.HELD if ends_at <= now else VisitState.PLANNED


class VisitNotFound(Exception):
    """No visit with this identifier is visible to the caller: missing and not visible are the
    same answer (ADR-0003 addendum of EKO-3-01, section 3; ADR-0003-C42)."""


class NotPlanned(Enum):
    """Why a create stored nothing once its body passed: the customer is outside the caller's own
    records or exists nowhere, or it is the caller's own and archived (scope before state)."""

    MISSING = "missing"
    ARCHIVED = "archived"


def own_address(raw: str | None) -> str | None:
    """Trimmed, then NFC, at most `OWN_ADDRESS_LIMIT` characters, stored as text; `None`, `""`
    and whitespace only are not given (K-03). The message never repeats the value."""
    value = given(raw)
    if value is None:
        return None
    address = stored_text(value.strip())
    if len(address) > OWN_ADDRESS_LIMIT:
        raise ValueError(f"at most {OWN_ADDRESS_LIMIT} characters")
    return address


def check_end_after_start(starts_at: datetime, ends_at: datetime) -> None:
    """The resolved instants compared, never the wall times (ADR-0002 *Wall time*)."""
    if ends_at <= starts_at:
        raise ValueError(END_NOT_AFTER_START)


@dataclass(frozen=True)
class VisitDraft:
    """A visit as a create asks for it: every value judged, both times instants."""

    customer_id: UUID
    starts_at: datetime
    ends_at: datetime
    own_address: str | None

    def __post_init__(self) -> None:
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("an instant needs its offset")
        check_end_after_start(self.starts_at, self.ends_at)


@dataclass(frozen=True)
class VisitCustomer:
    """The customer values a visit is shown with (ADR-0003-C42: identifier, name and current
    address), read under the visit's scope (A-3 A)."""

    id: UUID
    name: str
    address: Address


@dataclass(frozen=True)
class Visit:
    id: UUID
    customer: VisitCustomer
    starts_at: datetime
    ends_at: datetime
    own_address: str | None


@dataclass(frozen=True)
class ShownVisit:
    """A visit with its state at the instant it was read."""

    visit: Visit
    state: VisitState


def shown(visit: Visit, now: datetime) -> ShownVisit:
    return ShownVisit(visit, state_at(visit.ends_at, now))
