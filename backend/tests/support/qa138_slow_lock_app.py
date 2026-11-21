"""EKO-1-38 QA contrast factory: the observed blocker application of
`tests/support/eko138_observed_app.py`, with one tagged request pausing between its two
non-retried checkouts; none of this ships.

The request tagged `SLOW_TAG` sleeps `GAP_SECONDS` after its `find` returned and before its
`refresh_holder` checkout starts. During the pause it holds no connection and is not yet in the
waiting phase, so blockers placed then make that second checkout wait the pool timeout.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI

from app.data.sessions import RefreshHolder
from tests.support import eko138_observed_app as observed

SLOW_TAG = "6"
GAP_SECONDS = 0.3


class SlowLockStore(observed.ObservedStore):
    @contextmanager
    def refresh_holder(self, session_id: int) -> Iterator[RefreshHolder | None]:
        if observed._tag.get() == SLOW_TAG:
            time.sleep(GAP_SECONDS)
        with super().refresh_holder(session_id) as holder:
            yield holder


def create_with_blockers() -> FastAPI:
    app = observed.create_with_blockers()
    auth = app.state.auth
    auth.store = SlowLockStore(app.state.database, auth.phases)
    return app
