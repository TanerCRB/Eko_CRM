"""Entry point of the `worker` service (ADR-0006): `python -m app.worker`.

The walking skeleton's worker does no work. It never runs migrations; at start, in the main
process, it refuses a database revision other than its code's head or a recorded descendant
(ADR-0006-C13, ADR-0004 addendum 2026-10-29).
"""

import logging
import signal
import sys
import threading
from types import FrameType

from app.core.logs import install_process_logging
from app.core.settings import Settings, load_settings
from app.data.schema_revision import refuse_unless_servable

logger = logging.getLogger("app.worker")


def run(stop: threading.Event) -> int:
    load_settings(Settings)
    logger.info("worker started; no jobs are defined")
    stop.wait()
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
