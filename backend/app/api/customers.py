"""Customers: create, read by identifier, plain list (EKO-3-01; CUS-1, CUS-2, CUS-8, C-1 A to
C-3 A, Q-L A, Q-O A), with the address and tax identifier of EKO-3-02 (CUS-3 to CUS-5), the
list's search `q` and owner filter `owner` (EKO-3-04; ACC-4, PRH-4, ACC-8), and edit, archive,
restore and the list's `state` filter (EKO-3-05; CUS-9, ACC-5; gate-1 decision D-1).

The handlers pass the caller value inward and decide nothing about ownership (ADR-0003 addendum
of EKO-3-01, section 2). The request models hold the value rules of `app.domain.customers`, so a
rejected request is answered 422 before any service runs and nothing is stored; an edit is
judged by the create request model itself, on the body alone (EKO-3-05 Q-5, G-6 A). A customer
outside the caller's scope is answered exactly as one that exists nowhere: 404 `not found`. No
response names the owner (Q-O A) or the archived instant (Q-4 B). Every response here carries
`Cache-Control: no-store`, set for all of `/api/` in `main.py` (ADR-0005-C12); path parameters
are UUIDs only (ADR-0005-C13).
"""

import re
from collections.abc import Callable
from typing import Annotated, Any, Literal
from urllib.parse import unquote_plus, unquote_to_bytes
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    StrictBool,
    StrictStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import ErrorDetails, InitErrorDetails

from app.api.auth import Problem
from app.api.dependencies import get_clock, get_database
from app.auth.gate import AccessFirstRoute, current_caller
from app.core.clock import Clock
from app.data.customers import CustomerStore
from app.data.database import Database
from app.domain import customers as rules
from app.domain.caller import Caller
from app.domain.customers import (
    Contact,
    ContactKind,
    Customer,
    CustomerDraft,
    CustomerSearch,
    CustomerSummary,
    StateFilter,
)
from app.domain.ownership import owner_filter
from app.services import customers as service

router = APIRouter(prefix="/customers", route_class=AccessFirstRoute)


SURROGATES = re.compile("[\\ud800-\\udfff]")


class RequestModel(BaseModel):
    """A request body that refuses unknown keys with one error, not one per key (fix round 3,
    decision D on Issue #195): pydantic-core would build an `extra_forbidden` per key, and a
    2 MiB body holds 184 000 of them. The keys are scanned once; the known ones are validated as
    before, so their errors keep their own `loc`, and only the first unknown key is named. A key
    holding a lone surrogate gives pydantic's own single `string_unicode`, as before.
    `extra="forbid"` stays as the backstop."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="wrap")
    @classmethod
    def _one_unknown_key_error(cls, data: Any, handler: ModelWrapValidatorHandler[Any]) -> Any:
        if not isinstance(data, dict):
            return handler(data)
        fields = cls.model_fields
        first: str | None = None
        for key in data:
            if key in fields:
                continue
            if isinstance(key, str) and not key.isascii() and SURROGATES.search(key):
                raise ValidationError.from_exception_data(
                    cls.__name__, [{"type": "string_unicode", "loc": (), "input": data}]
                )
            if first is None:
                first = key
        if first is None:
            return handler(data)
        details: list[InitErrorDetails] = []
        try:
            handler({key: value for key, value in data.items() if key in fields})
        except ValidationError as known:
            details = [_detail(error) for error in known.errors(include_url=False)]
        details.append({"type": "extra_forbidden", "loc": (first,), "input": data[first]})
        raise ValidationError.from_exception_data(cls.__name__, details)


def _detail(error: ErrorDetails) -> InitErrorDetails:
    detail: InitErrorDetails = {"type": error["type"], "loc": error["loc"], "input": error["input"]}
    if "ctx" in error:
        detail["ctx"] = error["ctx"]
    return detail


class ContactIn(RequestModel):
    kind: Literal["phone", "email"]
    value: Annotated[StrictStr, Field(max_length=rules.VALUE_RAW_LIMIT)]
    # Who the contact reaches; omitted, `null` or `""` is no note.
    note: Annotated[StrictStr, Field(max_length=rules.NOTE_RAW_LIMIT)] | None = None
    primary: StrictBool = False

    @field_validator("value", "note")
    @classmethod
    def _judged(cls, value: str | None, info: ValidationInfo) -> str | None:
        # Without a valid kind the request is already refused for it; the value is not judged.
        kind = info.data.get("kind")
        judged_kind = None if kind is None else ContactKind(kind)
        return rules.contact_field(str(info.field_name), value, judged_kind)


class CustomerCreate(RequestModel):
    """A new customer, or the whole of an edited one (EKO-3-05 Q-5: the edit's request model is
    this one, so an edit is judged exactly as a create). The owner is never part of the request:
    an unknown field is a 422.

    The address and the tax ID are optional; omitted, `null`, `""` or whitespace only is not
    given (G-2 A). The country decides their rules (C-3 A); `tax_id` is a NIP for Poland and
    free text for any other country, stored apart by `TaxId.placed`.
    """

    name: Annotated[StrictStr, Field(max_length=rules.NAME_RAW_LIMIT)]
    # Omitted: Poland. `null`, `""` or a code outside the closed list: rejected (G-2 A, G-3 A).
    # The list is an enum on the request only; the answer types the country as a string, so a
    # code added later does not break it.
    country: Annotated[
        StrictStr, Field(max_length=2, json_schema_extra={"enum": sorted(rules.COUNTRY_CODES)})
    ] = rules.DEFAULT_COUNTRY
    street: Annotated[StrictStr, Field(max_length=rules.STREET_RAW_LIMIT)] | None = None
    postal_code: Annotated[StrictStr, Field(max_length=rules.POSTAL_CODE_RAW_LIMIT)] | None = None
    town: Annotated[StrictStr, Field(max_length=rules.TOWN_RAW_LIMIT)] | None = None
    # Declared after `country` and before `county`: a validator sees only the fields before it.
    voivodeship: Annotated[StrictStr, Field(max_length=rules.REGION_RAW_LIMIT)] | None = None
    county: Annotated[StrictStr, Field(max_length=rules.REGION_RAW_LIMIT)] | None = None
    tax_id: Annotated[StrictStr, Field(max_length=rules.TAX_ID_RAW_LIMIT)] | None = None
    contacts: list[ContactIn] = Field(default_factory=list, max_length=rules.CONTACT_LIMIT)

    # Every field through the one composition of create's rules in `app.domain.customers`, which
    # the operator seed uses too (EKO-3-06 A-5 A); fields are declared in `CUSTOMER_FIELDS` order.
    @field_validator(*rules.CUSTOMER_FIELDS)
    @classmethod
    def _judged(cls, value: str | None, info: ValidationInfo) -> str | None:
        return rules.customer_field(str(info.field_name), value, info.data)

    @model_validator(mode="after")
    def _contacts(self) -> "CustomerCreate":
        rules.check_contacts([_contact(c) for c in self.contacts])
        return self

    def draft(self) -> CustomerDraft:
        values = {field: getattr(self, field) for field in rules.CUSTOMER_FIELDS}
        return rules.assembled(values, [_contact(c) for c in self.contacts])


# The largest create body whose every field passes its raw cap: each code point at most 12 bytes
# (an astral character written as two `\uXXXX` escapes), plus the keys, quotes and separators of
# the object and of each contact, generously. Insignificant JSON whitespace is not counted.
_ESCAPED_BYTES_PER_CODE_POINT = 12
# The keys of the address and the tax ID (EKO-3-02) added to the object's own framing.
_OBJECT_FRAMING = 256
_CONTACT_FRAMING = 128
_ADDRESS_AND_TAX_ID_RAW = (
    rules.STREET_RAW_LIMIT
    + rules.POSTAL_CODE_RAW_LIMIT
    + rules.TOWN_RAW_LIMIT
    + 2 * rules.REGION_RAW_LIMIT
    + rules.TAX_ID_RAW_LIMIT
)
LARGEST_CREATE_BODY = (
    _OBJECT_FRAMING
    + _ESCAPED_BYTES_PER_CODE_POINT * (rules.NAME_RAW_LIMIT + _ADDRESS_AND_TAX_ID_RAW)
    + rules.CONTACT_LIMIT
    * (
        _CONTACT_FRAMING
        + _ESCAPED_BYTES_PER_CODE_POINT * (rules.VALUE_RAW_LIMIT + rules.NOTE_RAW_LIMIT)
    )
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
    """The customer as stored; every address part and the tax ID is `null` when not given. The
    tax ID is the Polish customer's canonical NIP or the foreign customer's text. `archived` is
    the stored state (EKO-3-05); the instant of archiving is never answered (Q-4 B)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    country: str
    street: str | None
    postal_code: str | None
    town: str | None
    voivodeship: str | None
    county: str | None
    tax_id: str | None
    contacts: list[ContactOut]
    archived: bool

    @classmethod
    def of(cls, customer: Customer) -> "CustomerOut":
        address = customer.address
        return cls(
            id=customer.id,
            name=customer.name,
            country=customer.country,
            street=address.street,
            postal_code=address.postal_code,
            town=address.town,
            voivodeship=address.voivodeship,
            county=address.county,
            tax_id=customer.tax_id.value,
            contacts=[
                ContactOut(kind=c.kind.value, value=c.value, note=c.note, primary=c.primary)
                for c in customer.contacts
            ],
            archived=customer.archived,
        )


class CustomerItem(BaseModel):
    """A listed customer; `archived` is its stored state, never the state the list asked for."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    country: str
    archived: bool

    @classmethod
    def of(cls, customer: CustomerSummary) -> "CustomerItem":
        return cls(
            id=customer.id,
            name=customer.name,
            country=customer.country,
            archived=customer.archived,
        )


class CustomerList(BaseModel):
    """The caller's visible customers that the search selects, with no sort order guaranteed
    (C-2 A) and no paging (EKO-3-04, G-7 A). It carries no count or other field (D-1)."""

    model_config = ConfigDict(extra="forbid")

    items: list[CustomerItem]


# CUS-6 as fixed at gate 1 of EKO-3-03 (A-2 A): one English sentence, ASCII only.
NIP_TAKEN = "a customer with this NIP already exists - contact your manager"


class NipTakenProblem(BaseModel):
    """The 409 of a create or an edit whose Polish NIP another stored customer holds, whoever owns
    it (CUS-6). The text is the same for every caller and names no customer, owner, count or NIP.
    Only a caller whose scope is all records gets `existing_customer_id`; for any other caller
    the field is absent, never `null` (ADR-0003-C38, gate 1 of EKO-3-03; ADR-0003-C40). The
    edit's other 409, `{"detail":"restore it first"}`, is an instance of it too (D-6 X-4 A)."""

    model_config = ConfigDict(extra="forbid")

    detail: str
    # Absent rather than `null`: the schema shows no null, and the answer drops a `None`.
    existing_customer_id: UUID | SkipJsonSchema[None] = None

    def body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem},
    403: {"model": Problem},
    503: {"model": Problem},
}


def customer_store(database: Annotated[Database, Depends(get_database)]) -> CustomerStore:
    return CustomerStore(database)


Store = Annotated[CustomerStore, Depends(customer_store)]
CurrentCaller = Annotated[Caller, Depends(current_caller)]
CurrentClock = Annotated[Clock, Depends(get_clock)]

LIST_PARAMETERS = ("q", "owner", "state")


def _undecodable(query_string: bytes) -> set[str]:
    """The list parameters whose value as sent is not percent-encoded UTF-8. The framework
    decodes such a value with replacement characters, so it is judged on the raw query."""
    found = set()
    for pair in query_string.split(b"&"):
        name, _, value = pair.partition(b"=")
        key = unquote_plus(name.decode("latin-1"))
        if key not in LIST_PARAMETERS:
            continue
        try:
            unquote_to_bytes(value.replace(b"+", b" ")).decode("utf-8")
        except UnicodeDecodeError:
            found.add(key)
    return found


def _query_value[T](
    name: str, rule: Callable[[str], T], raw: str, errors: list[dict[str, Any]]
) -> T | None:
    try:
        judged: T = rule(raw)
    except ValueError as exc:
        # A fixed message: the value itself is never repeated (ADR-0005).
        errors.append(
            {"type": "value_error", "loc": ("query", name), "msg": f"Value error, {exc}",
             "ctx": {"error": str(exc)}}
        )  # fmt: skip
        return None
    return judged


def customer_search(
    request: Request,
    q: Annotated[
        str,
        Query(
            max_length=rules.SEARCH_RAW_LIMIT,
            description="Text matched in the name, the town or a contact value, ignoring case.",
        ),
    ] = "",
    owner: Annotated[
        str,
        Query(description="An owner subject; it narrows the caller's visible customers only."),
    ] = "",
    state: Annotated[
        str,
        Query(
            description="Which customers by state: active (empty or absent), archived or both.",
            # Empty is accepted and means active, so it is listed with the closed set.
            json_schema_extra={"enum": ["", *(s.value for s in StateFilter)]},
        ),
    ] = "",
) -> CustomerSearch:
    """The list's query parameters, judged before any service runs; a refusal is a 422 naming
    the parameter and repeating no value (ADR-0005). Empty is not given (G-5 A); for `state`,
    not given is active (EKO-3-05 G-2 A)."""
    errors: list[dict[str, Any]] = []
    undecodable = _undecodable(request.scope.get("query_string", b""))
    for name in sorted(undecodable, key=LIST_PARAMETERS.index):
        errors.append(
            {"type": "string_unicode", "loc": ("query", name),
             "msg": "Input should be a valid string"}
        )  # fmt: skip
    term = None if "q" in undecodable else _query_value("q", rules.search_term, q, errors)
    subject = None if "owner" in undecodable else _query_value("owner", owner_filter, owner, errors)
    selected = (
        None if "state" in undecodable else _query_value("state", rules.state_filter, state, errors)
    )
    if errors or selected is None:
        raise RequestValidationError(errors)
    return CustomerSearch(term=term, owner=subject, state=selected)


Search = Annotated[CustomerSearch, Depends(customer_search)]


@router.post(
    "",
    operation_id="customer_create",
    status_code=201,
    response_model=CustomerOut,
    responses={**_REFUSALS, 409: {"model": NipTakenProblem}},
)
def create_customer(body: CustomerCreate, caller: CurrentCaller, store: Store) -> CustomerOut:
    return CustomerOut.of(service.create_customer(store, caller, body.draft()))


@router.get(
    "",
    operation_id="customer_list",
    response_model=CustomerList,
    responses=_REFUSALS,
)
def list_customers(caller: CurrentCaller, store: Store, search: Search) -> CustomerList:
    found = service.list_customers(store, caller, search)
    return CustomerList(items=[CustomerItem.of(c) for c in found])


@router.get(
    "/{customer_id}",
    operation_id="customer_read",
    response_model=CustomerOut,
    responses={**_REFUSALS, 404: {"model": Problem}},
)
def read_customer(customer_id: UUID, caller: CurrentCaller, store: Store) -> CustomerOut:
    return CustomerOut.of(service.read_customer(store, caller, customer_id))


@router.put(
    "/{customer_id}",
    operation_id="customer_edit",
    response_model=CustomerOut,
    # 409: archived, `{"detail":"restore it first"}` (G-4 A, D-2 S-2 A), or the NIP taken as on
    # create (ADR-0003-C40); one schema for both, told apart by `detail` (D-6 X-4 A).
    responses={**_REFUSALS, 404: {"model": Problem}, 409: {"model": NipTakenProblem}},
)
def edit_customer(
    customer_id: UUID, body: CustomerCreate, caller: CurrentCaller, store: Store
) -> CustomerOut:
    """The whole customer as the body states it (G-6 A); its contacts are replaced (G-5 A)."""
    return CustomerOut.of(service.edit_customer(store, caller, customer_id, body.draft()))


@router.post(
    "/{customer_id}/archive",
    operation_id="customer_archive",
    response_model=CustomerOut,
    responses={**_REFUSALS, 404: {"model": Problem}},
)
def archive_customer(
    customer_id: UUID, caller: CurrentCaller, store: Store, clock: CurrentClock
) -> CustomerOut:
    return CustomerOut.of(service.archive_customer(store, caller, customer_id, clock))


@router.post(
    "/{customer_id}/restore",
    operation_id="customer_restore",
    response_model=CustomerOut,
    responses={**_REFUSALS, 404: {"model": Problem}},
)
def restore_customer(customer_id: UUID, caller: CurrentCaller, store: Store) -> CustomerOut:
    return CustomerOut.of(service.restore_customer(store, caller, customer_id))
