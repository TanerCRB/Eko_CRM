"""Visit use cases (EKO-4-01): plan a visit, read one by identifier, and list the caller's visits,
all of them or those of a period of Europe/Warsaw dates.

Each receives the caller value and takes its scope only from `app.domain.ownership`, so the
ownership rule is decided there and applied by `app.data.visits`; nothing here compares an owner
(ADR-0003-C42). A create's answers come in the order C42 fixes: the creation scope (403 for a
caller without `rep`), the customer under the caller's own records (404), for an all-records
caller a customer it can read but does not own (403), and only then the own customer's archived
state (409). The state of every visit answered is derived from the injected clock, read once per
operation, never from the system time (ADR-0002-C13).
"""

from uuid import UUID

from app.core.clock import Clock
from app.data.customers import CustomerStore
from app.data.visits import VisitStore
from app.domain.caller import Caller
from app.domain.customers import CustomerArchived, CustomerNotFound
from app.domain.ownership import (
    NotPermitted,
    not_permitted_scope,
    visibility_scope,
    visit_creation_scope,
)
from app.domain.visits import NotPlanned, ShownVisit, VisitDraft, VisitNotFound, shown
from app.domain.warsaw import Period


def plan_visit(
    store: VisitStore, customers: CustomerStore, caller: Caller, draft: VisitDraft, clock: Clock
) -> ShownVisit:
    planned = store.create(visit_creation_scope(caller), draft)
    if planned is NotPlanned.ARCHIVED:
        raise CustomerArchived
    if planned is NotPlanned.MISSING:
        # Asked only for a caller the ownership rule lets know (gate 1 A-2 A); a rep without
        # `manager` is answered as for a customer that exists nowhere.
        wider = not_permitted_scope(caller)
        if wider is not None and customers.find(wider, draft.customer_id) is not None:
            raise NotPermitted
        raise CustomerNotFound
    return shown(planned, clock.now())


def read_visit(store: VisitStore, caller: Caller, visit_id: UUID, clock: Clock) -> ShownVisit:
    found = store.find(visibility_scope(caller), visit_id)
    if found is None:
        raise VisitNotFound
    return shown(found, clock.now())


def list_visits(
    store: VisitStore, caller: Caller, period: Period | None, clock: Clock
) -> list[ShownVisit]:
    """The caller's visible visits, narrowed by the period when one is given; a request value
    never becomes the scope."""
    found = store.find_all(visibility_scope(caller), period)
    now = clock.now()
    return [shown(visit, now) for visit in found]
