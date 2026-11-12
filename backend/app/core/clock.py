"""The one clock of `backend/app/` (ADR-0002 *Now, today*, ADR-0002-C13).

`now()` is the current instant as an aware UTC value. `monotonic()` and `sleep()` measure and
spend elapsed time for bounded waits; they never stand for a point in time. Code that needs any
of them receives a `Clock`, so a test fixes or moves it.
"""

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
