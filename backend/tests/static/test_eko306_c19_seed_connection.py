"""EKO-3-06, ADR-0003-C19 as restated (A-7 A): the application role's budget counts one
connection of the operator seed, a one-off of `worker` beside the running one.

With the composition's values the sum is 2 x (5 + 5) + 2 + 1 + 1 = 24 against the limit of 30.
The budget is the same function the runtime test applies to the values the running containers
received (tests/runtime/test_k03_roles_and_budget.py). That a seed run holds at most one
connection is the seed's own claim (developer-backend), not proven here.
"""

import dataclasses

from tests.static.test_k02_k03_check_contrasts import GOOD_BUDGET
from tests.support import db_checks as dc

# backend 2 x (5 + 5), worker 2 + 0, migrate 1, the operator seed 1.
WITH_THE_SEED = 24


def test_eko306_c19_the_composition_values_fit_the_limit_with_the_seed() -> None:
    assert GOOD_BUDGET.app_limit == 30
    assert dc.c19_violations(GOOD_BUDGET) == []


def test_eko306_c19_a_limit_of_exactly_the_sum_with_the_seed_holds() -> None:
    assert dc.c19_violations(dataclasses.replace(GOOD_BUDGET, app_limit=WITH_THE_SEED)) == []


def test_eko306_c19_a_limit_that_leaves_no_room_for_the_seed_fails() -> None:
    """The sum without the seed (23) fits a limit of 23; with the seed's connection it does not."""
    short = dataclasses.replace(GOOD_BUDGET, app_limit=WITH_THE_SEED - 1)
    assert dc.c19_violations(short) == [
        f"application connections at most {WITH_THE_SEED} > limit {WITH_THE_SEED - 1}"
    ]
