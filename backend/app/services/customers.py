"""Customer use cases (EKO-3-01): create, read by identifier, and the list, searched and filtered
by owner since EKO-3-04; edit, archive, restore and the list's state filter since EKO-3-05.

Each receives the caller value and takes its scope only from `app.domain.ownership`, so the
ownership rule is decided there and applied by `app.data.customers`; nothing here compares an
owner (ADR-0003 addendum of EKO-3-01, section 2). A change takes the visibility scope, never the
creation scope (EKO-3-05 Q-3 A, ADR-0003-C38): the manager changes any customer, a rep its own.
"""

from uuid import UUID

from app.core.clock import Clock
from app.data.customers import CustomerStore
from app.domain.caller import Caller
from app.domain.customers import (
    Customer,
    CustomerArchived,
    CustomerDraft,
    CustomerNotFound,
    CustomerSearch,
    CustomerSummary,
    Unchanged,
)
from app.domain.ownership import creation_scope, visibility_scope


def create_customer(store: CustomerStore, caller: Caller, draft: CustomerDraft) -> Customer:
    return store.create(creation_scope(caller), draft)


def read_customer(store: CustomerStore, caller: Caller, customer_id: UUID) -> Customer:
    return _found(store.find(visibility_scope(caller), customer_id))


def edit_customer(
    store: CustomerStore, caller: Caller, customer_id: UUID, draft: CustomerDraft
) -> Customer:
    """The whole customer replaced by `draft`; an archived one is refused, but only once the
    scope selected it, so another rep's customer is missing whatever its state (G-4 A)."""
    edited = store.edit(visibility_scope(caller), customer_id, draft)
    if edited is Unchanged.MISSING:
        raise CustomerNotFound
    if edited is Unchanged.ARCHIVED:
        raise CustomerArchived
    return edited


def archive_customer(
    store: CustomerStore, caller: Caller, customer_id: UUID, clock: Clock
) -> Customer:
    """Archived at the clock's instant; a repeat succeeds and keeps the first instant (K-04)."""
    return _found(store.archive(visibility_scope(caller), customer_id, clock.now()))


def restore_customer(store: CustomerStore, caller: Caller, customer_id: UUID) -> Customer:
    """Active again; restoring an active customer succeeds and changes nothing (K-04)."""
    return _found(store.restore(visibility_scope(caller), customer_id))


def list_customers(
    store: CustomerStore, caller: Caller, search: CustomerSearch
) -> list[CustomerSummary]:
    """The caller's scope, narrowed by the search; a request value never becomes the scope, so a
    rep naming another owner gets the answer of a search that matches nothing (G-3 A)."""
    return store.find_all(visibility_scope(caller), search)


def _found(customer: Customer | None) -> Customer:
    if customer is None:
        raise CustomerNotFound
    return customer
