"""Session and login-transaction limits chosen at gate 1 of EKO-2-01 (ADR-0003 addendum of
2026-11-02, G-1 A; ADR-0003 *Browser flow*; ADR-0005 *Retention*)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

IDLE_LIMIT = timedelta(minutes=30)
ABSOLUTE_LIMIT = timedelta(hours=10)
LOGIN_TRANSACTION_VALIDITY = timedelta(minutes=10)
# Retention bounds count from creation; "no later than" includes the bound (ADR-0005).
SESSION_RETENTION = ABSOLUTE_LIMIT
LOGIN_TRANSACTION_RETENTION = timedelta(hours=1)


@dataclass(frozen=True)
class SessionTimes:
    created_at: datetime
    last_used_at: datetime

    def usable_at(self, now: datetime) -> bool:
        """Works immediately before each deadline; refused at and after it."""
        return now < self.created_at + ABSOLUTE_LIMIT and now < self.last_used_at + IDLE_LIMIT


def login_transaction_valid_at(created_at: datetime, now: datetime) -> bool:
    return now < created_at + LOGIN_TRANSACTION_VALIDITY
