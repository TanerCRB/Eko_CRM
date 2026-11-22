"""Customer use cases (EKO-3-01): create, read by identifier, and the list, searched and filtered
by owner since EKO-3-04.

Each receives the caller value and takes its scope only from `app.domain.ownership`, so the
ownership rule is decided there and applied by `app.data.customers`; nothing here compares an
owner (ADR-0003 addendum of EKO-3-01, section 2).
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
)
from app.domain.ownership import creation_scope, visibility_scope


def create_customer(store: CustomerStore, caller: Caller, draft: CustomerDraft) -> Customer:
    return store.create(creation_scope(caller), draft)


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
