"""Customer use cases (EKO-3-01): create, read by identifier, and the list, searched and filtered
by owner since EKO-3-04; edit, archive, restore and the list's state filter since EKO-3-05.

Each receives the caller value and takes its scope only from `app.domain.ownership`, so the
ownership rule is decided there and applied by `app.data.customers`; nothing here compares an
owner (ADR-0003 addendum of EKO-3-01, section 2). A change takes the visibility scope, never the
creation scope (EKO-3-05 Q-3 A, ADR-0003-C41): the manager changes any customer, a rep its own.
A create or an edit refused for a taken NIP (EKO-3-03; ADR-0003-C40) names the stored customer
only to a caller that rule gives a reference.
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
    NipTaken,
    Unchanged,
)
from app.domain.ownership import creation_scope, reference_scope, visibility_scope


def create_customer(store: CustomerStore, caller: Caller, draft: CustomerDraft) -> Customer:
    """`creation_scope` decides first, so a caller without `rep` is refused before any NIP is
    judged. A taken NIP is refused by the insert; the stored customer is then read under the
    reference scope, never under the caller's own (ADR-0003-C38)."""
    scope = creation_scope(caller)
    try:
        return store.create(scope, draft)
    except NipTaken:
        raise _with_reference(store, caller, draft) from None


def read_customer(store: CustomerStore, caller: Caller, customer_id: UUID) -> Customer:
    return _found(store.find(visibility_scope(caller), customer_id))


def edit_customer(
    store: CustomerStore, caller: Caller, customer_id: UUID, draft: CustomerDraft
) -> Customer:
    """The whole customer replaced by `draft`; an archived one is refused, but only once the
    scope selected it, so another rep's customer is missing whatever its state (G-4 A). A NIP
    another customer holds is refused only for a target inside the scope and active, by the
    scoped `UPDATE` itself, and answered exactly as create's (ADR-0003-C40)."""
    try:
        edited = store.edit(visibility_scope(caller), customer_id, draft)
    except NipTaken:
        # The same reference rule as create's; never the caller's visibility scope (C40).
        raise _with_reference(store, caller, draft) from None
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


def _with_reference(store: CustomerStore, caller: Caller, draft: CustomerDraft) -> NipTaken:
    """The NIP-taken refusal, naming the stored customer only under the reference scope: every
    record for a caller holding `manager`, none for any other (ADR-0003-C38, C40)."""
    reference = reference_scope(caller)
    nip = draft.tax_id.nip
    if reference is None or nip is None:
        return NipTaken()
    return NipTaken(store.find_by_nip(reference, nip))
