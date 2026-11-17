from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """The application's roles (ADR-0003 *Roles*); a caller is granted the union of its roles."""

    REP = "rep"
    MANAGER = "manager"
    ADMINISTRATOR = "administrator"


# `administrator` grants no CRM data: it is absent here, so it adds nothing to a caller's rights.
CRM_DATA_ROLES = frozenset({Role.REP, Role.MANAGER})


@dataclass(frozen=True)
class Caller:
    """The authenticated staff member passed inward from the access dependency (ADR-0003 *Roles*).

    `subject` is the identity server's `sub`, compared exactly; `roles` are the application roles
    the verified token holds for this request.
    """

    subject: str
    name: str | None
    roles: frozenset[Role]

    @property
    def has_any_role(self) -> bool:
        return bool(self.roles)

    @property
    def may_use_crm_data(self) -> bool:
        """Reading or changing customers, visits, notes, actions or dashboards."""
        return not self.roles.isdisjoint(CRM_DATA_ROLES)

    @property
    def has_manager_rights(self) -> bool:
        return Role.MANAGER in self.roles
