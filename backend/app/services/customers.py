"""Customer use cases (EKO-3-01): create, read by identifier, and the list, searched and filtered
by owner since EKO-3-04.

Each receives the caller value and takes its scope only from `app.domain.ownership`, so the
ownership rule is decided there and applied by `app.data.customers`; nothing here compares an
owner (ADR-0003 addendum of EKO-3-01, section 2). A create refused for a taken NIP (EKO-3-03)
names the stored customer only to a caller that rule gives a reference.
"""

from uuid import UUID

from app.data.customers import CustomerStore
from app.domain.caller import Caller
from app.domain.customers import (
    Customer,
    CustomerDraft,
    CustomerNotFound,
    CustomerSearch,
    CustomerSummary,
    NipTaken,
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
        reference = reference_scope(caller)
        nip = draft.tax_id.nip
        if reference is None or nip is None:
            raise
        raise NipTaken(store.find_by_nip(reference, nip)) from None


def read_customer(store: CustomerStore, caller: Caller, customer_id: UUID) -> Customer:
    found = store.find(visibility_scope(caller), customer_id)
    if found is None:
        raise CustomerNotFound
    return found


def list_customers(
    store: CustomerStore, caller: Caller, search: CustomerSearch
) -> list[CustomerSummary]:
    """The caller's scope, narrowed by the search; a request value never becomes the scope, so a
    rep naming another owner gets the answer of a search that matches nothing (G-3 A)."""
    return store.find_all(visibility_scope(caller), search)
