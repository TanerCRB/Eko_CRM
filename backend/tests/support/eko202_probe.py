"""EKO-2-02's probe routes and token role claims; none of this ships.

The probe is registered by the test process onto the application the shipped `create_app()`
built (gate-1 OQ-3 A, impact map section 2(a)): never in `backend/app/`, never exempted, never
behind a settings flag. It stands in for the CRM routes that arrive from EKO-3-01 on: one
customers-reading operation (GET, carrying a `role` query field) and one customers-changing
operation (POST, carrying a `role` body field), both declaring the product's CRM-data dependency;
one customers-reading operation declaring only the session dependency (`current_caller`, the
product's own pattern) and one declaring no dependency of its own, so the application-wide
default refusal is what keeps them closed (fix round 1, R-01); and one operation declaring the
product's manager dependency. Each handler that receives a caller identity hands it to
`Recorder.receive`, the stand-in for a `services` entry point, so a test reads what crossed inward
instead of an echo in a response.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, ConfigDict

from app.auth.gate import crm_data_caller, current_caller, manager_caller
from app.domain.caller import Caller
from tests.support.oidc_stub import CLIENT_ID

PREFIX = "/api/eko202-probe"
CUSTOMERS = f"{PREFIX}/customers"
TEAM = f"{PREFIX}/team"
SESSION_ONLY = f"{PREFIX}/customers-session-only"
UNDECLARED = f"{PREFIX}/customers-undeclared"
# CRM class only because no list marks them otherwise: neither declares a CRM dependency.
DEFAULT_CRM_OPERATIONS = frozenset({("GET", SESSION_ONLY), ("GET", UNDECLARED)})
CRM_DATA_OPERATIONS = frozenset({("GET", CUSTOMERS), ("POST", CUSTOMERS)}) | DEFAULT_CRM_OPERATIONS
MANAGER_OPERATIONS = frozenset({("GET", TEAM)})
OPERATIONS = CRM_DATA_OPERATIONS | MANAGER_OPERATIONS


class ProbeChange(BaseModel):
    # `role` is declared so a body naming it is accepted (not 422): the body channel stays live.
    model_config = ConfigDict(extra="forbid")

    role: Any = None


class Reached(BaseModel):
    operation: str


@dataclass
class Recorder:
    received: list[Caller] = field(default_factory=list)

    def receive(self, caller: Caller) -> None:
        self.received.append(caller)


def install_probe(app: FastAPI) -> Recorder:
    recorder = Recorder()

    @app.get(CUSTOMERS)
    def read_customers(
        caller: Annotated[Caller, Depends(crm_data_caller)],
        role: Annotated[list[str] | None, Query()] = None,
    ) -> Reached:
        recorder.receive(caller)
        return Reached(operation="read-customers")

    @app.post(CUSTOMERS)
    def change_customers(
        caller: Annotated[Caller, Depends(crm_data_caller)], change: ProbeChange | None = None
    ) -> Reached:
        recorder.receive(caller)
        return Reached(operation="change-customers")

    @app.get(SESSION_ONLY)
    def read_customers_session_only(caller: Annotated[Caller, Depends(current_caller)]) -> Reached:
        recorder.receive(caller)
        return Reached(operation="read-customers-session-only")

    @app.get(UNDECLARED)
    def read_customers_undeclared() -> Reached:
        return Reached(operation="read-customers-undeclared")

    @app.get(TEAM)
    def read_team(caller: Annotated[Caller, Depends(manager_caller)]) -> Reached:
        recorder.receive(caller)
        return Reached(operation="read-team")

    return recorder


def role_claims(
    client: list[Any] | Any | None = None,
    realm: list[Any] | None = None,
    other_clients: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Access-token claim overrides for the OIDC stub, in Keycloak's claim layout:
    `resource_access.<client>.roles` and `realm_access.roles`. `client=None` leaves the
    application's client out of `resource_access`, and with no other client the claim is
    removed (the stub drops a `None` claim), replacing the stub user's default `rep`; any other
    value is placed as given, so a malformed claim (a string instead of a list) can be minted."""
    resource: dict[str, Any] = {
        name: {"roles": roles} for name, roles in (other_clients or {}).items()
    }
    if client is not None:
        resource[CLIENT_ID] = {"roles": client}
    claims: dict[str, Any] = {"resource_access": resource or None}
    if realm is not None:
        claims["realm_access"] = {"roles": realm}
    return claims
