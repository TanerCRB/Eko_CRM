"""Entry point of the `worker` service (ADR-0006): `python -m app.worker`.

It never runs migrations; at start, in the main process, it refuses a database revision other than
its code's head or a recorded descendant (ADR-0006-C13, ADR-0004 addendum 2026-10-29). Its one job
is the retention of sessions and login transactions (ADR-0005 *Retention*, EKO-2-01).
"""

import logging
import signal
import sys
import threading
from types import FrameType

from app.core.clock import Clock, SystemClock
from app.core.logs import install_process_logging
from app.core.settings import Settings, load_settings
from app.data.database import Database
from app.data.schema_revision import refuse_unless_servable
from app.services.retention import run_once

logger = logging.getLogger("app.worker")

# The first sweep runs this long after start, so a stop requested at once touches no database.
FIRST_SWEEP_AFTER_SECONDS = 1.0


def run(stop: threading.Event, clock: Clock | None = None) -> int:
    database = Database.from_settings(load_settings(Settings))
    clock = clock or SystemClock()
    logger.info("worker started")
    try:
        wait = FIRST_SWEEP_AFTER_SECONDS
        while not stop.wait(wait):
            wait = run_once(database, clock)
    finally:
        database.dispose()
    logger.info("worker stopping")
    return 0


def main() -> None:
    install_process_logging("worker")
    refuse_unless_servable(load_settings(Settings), "worker")
    stop = threading.Event()

    def _request_stop(signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    sys.exit(run(stop))


if __name__ == "__main__":
    main()
