"""Staff use cases (EKO-3-08): the manager's list of reps.

Who may read it is decided once, by the route's manager check (`manager_caller`) on the token
verified for the request; nothing here reads a role, so no second check can hide a missing first.
"""

from app.data.staff import StaffStore
from app.domain.staff import Rep


def list_reps(store: StaffStore) -> list[Rep]:
    return store.reps()
