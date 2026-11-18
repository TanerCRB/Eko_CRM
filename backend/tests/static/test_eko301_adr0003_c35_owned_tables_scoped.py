"""EKO-3-01, ADR-0003-C35 (addendum of EKO-3-01, section 2, O-1 A): every function under
`backend/app/data/` that reads or changes rows of an owned table takes a visibility scope as a
required parameter with no default, and no module outside `backend/app/data/` refers to an owned
table. Run on the repository's sources and on planted fixtures, so the check can fail.
"""

from pathlib import Path

import pytest

from tests.support import ownership_checks as oc
from tests.support.repo import REPO_ROOT

APP = REPO_ROOT / "backend" / "app"
FIXTURE_PATH = "backend/app/data/planted.py"


def app_sources() -> dict[str, str]:
    return {
        p.relative_to(REPO_ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in APP.rglob("*.py")
    }


def test_c35_every_data_function_on_an_owned_table_takes_a_required_scope() -> None:
    sources = app_sources()
    reached = oc.owned_functions(sources)
    # Non-vacuity: the customer store's reads and its write are among them.
    assert {"create", "find", "find_all", "_visible"} <= {
        name.rsplit(":", 1)[1] for name in reached
    }, reached
    assert oc.unscoped_functions(sources) == []


def test_c35_no_module_outside_data_refers_to_an_owned_table() -> None:
    assert oc.outside_references(app_sources()) == []


SCOPED = """
from app.data.models import CustomerRow
from app.domain.ownership import VisibilityScope


def find(connection, scope: VisibilityScope, customer_id):
    return connection.execute(select(CustomerRow).where(visible(scope)))
"""

PLANTED = {
    "no-scope": """
from app.data.models import CustomerRow


def find_any(connection, customer_id):
    return connection.execute(select(CustomerRow).where(CustomerRow.id == customer_id))
""",
    "scope-with-default": """
from app.data.models import CustomerRow
from app.domain.ownership import AllRecords, VisibilityScope


def find(connection, customer_id, scope: VisibilityScope = AllRecords()):
    return connection.execute(select(CustomerRow).where(visible(scope)))
""",
    "scope-default-none": """
from app.data.models import CustomerContactRow


def contacts(connection, *, scope=None):
    return connection.execute(select(CustomerContactRow))
""",
    "untyped-scope": """
from app.data.models import CustomerRow


def find(connection, scope, customer_id):
    return connection.execute(select(CustomerRow))
""",
    "through-a-column-tuple": """
from app.data.models import CustomerRow

COLUMNS = (CustomerRow.id, CustomerRow.name)


def every_name(connection):
    return connection.execute(select(*COLUMNS))
""",
    "through-a-helper": """
from app.data.models import CustomerRow
from app.domain.ownership import VisibilityScope


def _rows(connection, scope: VisibilityScope):
    return connection.execute(select(CustomerRow).where(visible(scope)))


def everything(connection):
    return _rows(connection, ALL)
""",
    "a-method": """
from app.data.models import CustomerRow


class Store:
    def peek(self, customer_id):
        return self._c.execute(select(CustomerRow))
""",
    "raw-sql-string": """
from sqlalchemy import text


def count(connection):
    return connection.execute(text("SELECT count(*) FROM customer"))
""",
}


def test_c35_contrast_a_scoped_fixture_passes() -> None:
    assert oc.unscoped_functions({FIXTURE_PATH: SCOPED}) == []
    assert oc.owned_functions({FIXTURE_PATH: SCOPED}) == [f"{FIXTURE_PATH}:find"]


@pytest.mark.parametrize("variant", sorted(PLANTED))
def test_c35_contrast_an_unscoped_fixture_fails(variant: str) -> None:
    assert oc.unscoped_functions({FIXTURE_PATH: PLANTED[variant]}) != []


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("backend/app/services/planted.py", "from app.data.models import CustomerRow"),
        ("backend/app/api/planted.py", "rows = CustomerContactRow.__table__"),
        ("backend/app/services/planted.py", 'text("SELECT * FROM customer WHERE 1")'),
        ("backend/app/domain/planted.py", "TABLE = 'customer_contact'"),
    ],
)
def test_c35_contrast_a_reference_outside_data_fails(path: str, line: str) -> None:
    assert oc.outside_references({path: line + "\n"}) == [f"{path}:1"]


def test_c35_contrast_the_same_reference_inside_data_passes() -> None:
    path = "backend/app/data/planted.py"
    assert oc.outside_references({path: "from app.data.models import CustomerRow\n"}) == []


def test_c35_the_repository_sources_are_read() -> None:
    assert Path(APP / "data" / "models.py").relative_to(REPO_ROOT).as_posix() in app_sources()
