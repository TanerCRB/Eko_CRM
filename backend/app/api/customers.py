"""Customers: create, read by identifier, plain list (EKO-3-01; CUS-1, CUS-2, CUS-8, C-1 A to
C-3 A, Q-L A, Q-O A).

The handlers pass the caller value inward and decide nothing about ownership (ADR-0003 addendum
of EKO-3-01, section 2). The request models hold the value rules of `app.domain.customers`, so a
rejected request is answered 422 before any service runs and nothing is stored. A customer
outside the caller's scope is answered exactly as one that exists nowhere: 404 `not found`. No
response names the owner (Q-O A). Every response here carries `Cache-Control: no-store`, set for
all of `/api/` in `main.py` (ADR-0005-C12); path parameters are UUIDs only (ADR-0005-C13).
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.api.auth import Problem
from app.api.dependencies import get_database
from app.auth.gate import AccessFirstRoute, current_caller
from app.data.customers import CustomerStore
from app.data.database import Database
from app.domain import customers as rules
from app.domain.caller import Caller
from app.domain.customers import Contact, ContactKind, Customer, CustomerDraft, CustomerSummary
from app.services import customers as service

router = APIRouter(prefix="/customers", route_class=AccessFirstRoute)


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["phone", "email"]
    value: StrictStr
    # Who the contact reaches; omitted, `null` or `""` is no note.
    note: StrictStr | None = None
    primary: StrictBool = False

    @field_validator("value")
    @classmethod
    def _value(cls, value: str, info: ValidationInfo) -> str:
        kind = info.data.get("kind")
        # Without a valid kind the request is already refused for it; the value is not judged.
        return value if kind is None else rules.contact_value(ContactKind(kind), value)

    @field_validator("note")
    @classmethod
    def _note(cls, note: str | None) -> str | None:
        return rules.contact_note(note)


class CustomerCreate(BaseModel):
    """A new customer. The owner is never part of the request: an unknown field is a 422."""

    model_config = ConfigDict(extra="forbid")

    name: StrictStr
    # Omitted: Poland. `null`, `""` or a code outside the closed list: rejected (G-2 A, G-3 A).
    # The list is an enum on the request only; the answer types the country as a string, so a
    # code added later does not break it.
    country: Annotated[
        StrictStr, Field(json_schema_extra={"enum": sorted(rules.COUNTRY_CODES)})
    ] = rules.DEFAULT_COUNTRY
    contacts: list[ContactIn] = Field(default_factory=list, max_length=rules.CONTACT_LIMIT)

    @field_validator("name")
    @classmethod
    def _name(cls, name: str) -> str:
        return rules.customer_name(name)

    @field_validator("country")
    @classmethod
    def _country(cls, country: str) -> str:
        return rules.country_code(country)

    @model_validator(mode="after")
    def _contacts(self) -> "CustomerCreate":
        rules.check_contacts([_contact(c) for c in self.contacts])
        return self

    def draft(self) -> CustomerDraft:
        return CustomerDraft(
            name=self.name,
            country=self.country,
            contacts=tuple(_contact(c) for c in self.contacts),
        )


def _contact(contact: ContactIn) -> Contact:
    return Contact(ContactKind(contact.kind), contact.value, contact.note, contact.primary)


class ContactOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    value: str
    note: str | None
    primary: bool


class CustomerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    country: str
    contacts: list[ContactOut]

    @classmethod
    def of(cls, customer: Customer) -> "CustomerOut":
        return cls(
            id=customer.id,
            name=customer.name,
            country=customer.country,
            contacts=[
                ContactOut(kind=c.kind.value, value=c.value, note=c.note, primary=c.primary)
                for c in customer.contacts
            ],
        )


class CustomerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    country: str

    @classmethod
    def of(cls, customer: CustomerSummary) -> "CustomerItem":
        return cls(id=customer.id, name=customer.name, country=customer.country)


class CustomerList(BaseModel):
    """The caller's visible customers, with no sort order guaranteed (C-2 A; paging EKO-3-04)."""

    model_config = ConfigDict(extra="forbid")

    items: list[CustomerItem]


_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem},
    403: {"model": Problem},
    503: {"model": Problem},
}


def customer_store(database: Annotated[Database, Depends(get_database)]) -> CustomerStore:
    return CustomerStore(database)


Store = Annotated[CustomerStore, Depends(customer_store)]
CurrentCaller = Annotated[Caller, Depends(current_caller)]


@router.post(
    "",
    operation_id="customer_create",
    status_code=201,
    response_model=CustomerOut,
    responses=_REFUSALS,
)
def create_customer(body: CustomerCreate, caller: CurrentCaller, store: Store) -> CustomerOut:
    return CustomerOut.of(service.create_customer(store, caller, body.draft()))


@router.get(
    "",
    operation_id="customer_list",
    response_model=CustomerList,
    responses=_REFUSALS,
)
def list_customers(caller: CurrentCaller, store: Store) -> CustomerList:
    return CustomerList(items=[CustomerItem.of(c) for c in service.list_customers(store, caller)])


@router.get(
    "/{customer_id}",
    operation_id="customer_read",
    response_model=CustomerOut,
    responses={**_REFUSALS, 404: {"model": Problem}},
)
def read_customer(customer_id: UUID, caller: CurrentCaller, store: Store) -> CustomerOut:
    return CustomerOut.of(service.read_customer(store, caller, customer_id))
