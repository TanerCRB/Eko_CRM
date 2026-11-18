"""Record ownership (ADR-0003 addendum of EKO-3-01, sections 1 and 2; ACC-4, PRH-4).

The one place the rule lives: the caller value becomes a visibility scope, and creating a record
needs a creation scope. Every `data` function on an owned table takes one of them as a required
argument and applies it in the statement that selects or writes the rows (ADR-0003-C35), so a
record outside the scope is never loaded.
"""

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
