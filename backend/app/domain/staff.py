"""The staff display-name copy (ADR-0003 *Staff display name* A, *Staff personal data*; ADR-0003-C37
and ADR-0005 PD-S3 as extended by the EKO-3-08 addendum).

One copy per subject: the subject, the verified access token's `name` in NFC (or none), whether
that login's token held `rep`, and the instant of that login. Nothing else of the token. The copy
is never an authority: no caller value is built from it, and its rep item only selects the
entries of the manager's list of reps.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.caller import Role

# ADR-0005 *Retention* as counted by the EKO-3-08 addendum: 180 x 24 h between UTC instants, the
# bound included.
COPY_RETENTION = timedelta(hours=180 * 24)
# What PostgreSQL text cannot hold: U+0000, and a lone surrogate, which has no UTF-8 form.
UNSTORABLE = re.compile("[\\x00\\ud800-\\udfff]")


@dataclass(frozen=True)
class DisplayNameCopy:
    subject: str
    name: str | None
    is_rep: bool
    last_login_at: datetime


@dataclass(frozen=True)
class Rep:
    """An entry of the manager's list of reps: the subject and the display name, nothing else."""

    subject: str
    name: str | None


def display_name_copy(
    subject: str, name: str | None, roles: frozenset[Role], at: datetime
) -> DisplayNameCopy:
    """The copy of one login. The name is normalised to NFC and never trimmed: trimming belongs to
    comparison keys, not to a stored name (ADR-0002 *Polish text*). A name the database cannot
    hold is stored as none, so it never refuses the login (A-11)."""
    if name is not None:
        name = unicodedata.normalize("NFC", name)
    return DisplayNameCopy(
        subject=subject,
        name=None if name is None or UNSTORABLE.search(name) else name,
        is_rep=Role.REP in roles,
        last_login_at=at,
    )
