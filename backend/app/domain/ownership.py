"""Record ownership (ADR-0003 addendum of EKO-3-01, sections 1 and 2; ACC-4, PRH-4).

The one place the rule lives: the caller value becomes a visibility scope, and creating a record
needs a creation scope. Every `data` function on an owned table takes one of them as a required
argument and applies it in the statement that selects or writes the rows (ADR-0003-C35), so a
record outside the scope is never loaded.
"""

import re
from dataclasses import dataclass

from app.domain.caller import Caller, Role


class NotPermitted(Exception):
    """The caller's roles do not grant the operation on owned records: HTTP 403."""


@dataclass(frozen=True)
class AllRecords:
    """Every record: a caller holding `manager`."""


@dataclass(frozen=True)
class OwnedBy:
    """The records whose owner is `subject`, compared byte-wise."""

    subject: str


VisibilityScope = AllRecords | OwnedBy

# ADR-0003 addendum of EKO-3-04 (Q-3 A): the OpenID Connect bound on `sub`, printable ASCII only.
OWNER_LIMIT = 255
OWNER_SUBJECT = re.compile(rf"[\x21-\x7e]{{1,{OWNER_LIMIT}}}")


def visibility_scope(caller: Caller) -> VisibilityScope:
    """`manager` reads every record; `rep` without `manager` reads only its own. Roles combine,
    so `rep` and `manager` reads every record (ADR-0003 *Roles*)."""
    if caller.has_manager_rights:
        return AllRecords()
    if Role.REP in caller.roles:
        return OwnedBy(caller.subject)
    raise NotPermitted


def creation_scope(caller: Caller) -> OwnedBy:
    """Creating needs `rep`; the new record's owner is the caller, never a request value."""
    if Role.REP not in caller.roles:
        raise NotPermitted
    return OwnedBy(caller.subject)


def owner_filter(raw: str) -> str | None:
    """A request's owner filter: a subject as sent, never trimmed, folded or normalised, so it is
    compared byte-wise; `""` is no filter (G-5 A). It is judged on its form alone, never on
    whether anyone holds that subject, and it only narrows a scope: it never becomes one."""
    if raw == "":
        return None
    if not OWNER_SUBJECT.fullmatch(raw):
        raise ValueError(f"not an owner subject: 1 to {OWNER_LIMIT} printable ASCII characters")
    return raw
