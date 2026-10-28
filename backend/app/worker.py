"""Entry point of the `worker` service (ADR-0006): `python -m app.worker`.

The walking skeleton's worker does no work. It never runs migrations; the revision check at start
is EKO-1-11's.
"""

import logging
import signal
import sys
import threading
from types import FrameType

from app.core.settings import Settings, load_settings

logger = logging.getLogger("app.worker")


def run(stop: threading.Event) -> int:
    load_settings(Settings)
    logger.info("worker started; no jobs are defined")
    stop.wait()
    logger.info("worker stopping")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()

    def _request_stop(signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    sys.exit(run(stop))


if __name__ == "__main__":
    main()
