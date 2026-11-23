"""EKO-1-40 K-01 contrast (2), QA (#228): the same controlled checkout delay on the non-holder
process only, with the carrier body as it is at `b099acc`, shows no signature S.

One element changes against `test_eko140_k01_checkout_delay.py`: the factory delays the process
whose request found the lock taken (`create_delayed_on_non_holder`) instead of the holder's. The
verdict is read from both processes' records whether the carrier goes red or green: S absent, and
the delay in effect on the non-holder process only, so the absence cannot come from a delay that
never ran.

What this contrast does not show: S is defined on the holder's process, which is undelayed here, so
S being absent is expected by construction. The developer's runs of this contrast went red in 10 of
10 with a 503 from `find` on the delayed non-holder process (two free connections); that 503 is
recorded in `docs/evidence/EKO-1-40/`, not asserted here, because it is not part of S.
"""

from typing import Any

import pytest

from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.runtime.eko201.processes import Backend
from tests.support import oidc_stub
from tests.support.eko140_checkout_delay import DELAY_SECONDS
from tests.support.eko140_signature import holder_process, signature_s
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

ON_NON_HOLDER = "tests.support.eko140_checkout_delay:create_delayed_on_non_holder"

Record = dict[str, dict[str, Any]]


def recorded(record: Record) -> k04.Settle:
    """The carrier's `all_waiting`; when it fails, both processes' records are kept first."""

    def settle(stub: oidc_stub.Stub, sid: str, a: Backend, b: Backend) -> tuple[Backend, Backend]:
        try:
            return k04.all_waiting(stub, sid, a, b)
        except AssertionError:
            record.update(a=k04.observed(a), b=k04.observed(b))
            raise

    return settle


@pytest.mark.parametrize("late", [None, k04.LATE_SECONDS], ids=["on-time", "one-late"])
def test_eko140_qa_k01_the_same_delay_on_the_non_holder_process_only_shows_no_signature_s(
    pg: Postgres, stub: oidc_stub.Stub, late: float | None
) -> None:
    record: Record = {}
    try:
        run = k04.pool_exhausted_responsive(pg, stub, recorded(record), late, ON_NON_HOLDER)
    except AssertionError as red:
        # Only a red inside the settle leaves a record; any other red is not this contrast's.
        assert record, f"the run went red before or after the settle: {red}"
    else:
        record.update(run.final)
    holder = holder_process(record)
    assert holder is not None, record
    [other] = {"a", "b"} - {holder}
    assert signature_s(record) == [], record
    # The delay ran, and on the non-holder process only.
    delay = record[other]["delay"]
    assert (delay["on"], delay["seconds"]) == ("non-holder", DELAY_SECONDS), delay
    assert delay["applied"] > 0, delay
    assert record[holder]["delay"]["applied"] == 0, record[holder]["delay"]
