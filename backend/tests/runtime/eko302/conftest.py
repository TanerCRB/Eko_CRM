"""EKO-3-02 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, and the readers of
the stored customer row. Every value is synthetic (ADR-0005), NIPs built at run time (G-7 A).
"""

from typing import Any

from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko301.conftest import Crm

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers
crm = eko301.crm

NEW_FIELDS = ("street", "postal_code", "town", "voivodeship", "county", "tax_id")
STORED_COLUMNS = (
    "street",
    "postal_code",
    "town",
    "voivodeship",
    "county",
    "nip",
    "foreign_tax_id",
)
STORED_ROW = (
    "SELECT street, postal_code, town, voivodeship, county, nip, foreign_tax_id "
    "FROM customer WHERE id = %s"
)
NAME = "Gospodarstwo Testowe 302"


def stored(crm: Crm, customer_id: str) -> dict[str, Any]:
    """The new columns of the row as PostgreSQL holds them, read outside the API."""
    [row] = crm.pg.rows(STORED_ROW, (customer_id,))
    return dict(zip(STORED_COLUMNS, row, strict=True))


def new_fields(answer: dict[str, Any]) -> dict[str, Any]:
    return {name: answer[name] for name in NEW_FIELDS}


def errors_at(response: Any) -> list[tuple[Any, ...]]:
    """The `loc` of every error of a 422, without the leading `body`. An unknown field is also
    located at its key, so `extra_forbidden` is refused here: a field is judged by its rule."""
    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    assert all(error["type"] != "extra_forbidden" for error in errors), errors
    return [tuple(error["loc"][1:]) for error in errors]
