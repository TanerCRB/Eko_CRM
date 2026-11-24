"""EKO-3-08, ADR-0003-C35 as restated by the ADR-0003 addendum of EKO-3-08 (Q-2 A, a declared
deviation): a function under `backend/app/data/` that reads an owned table takes a required scope
or is on the closed system-read list held in the check. The list in the check equals the list
held here; a listed function that returns a column of an owned table fails; a listed function
reached from a module under `backend/app/api/` or `backend/app/auth/` fails. Run on the
repository's sources and on planted fixtures, so each half can fail.
"""

import pytest

from tests.static.test_eko301_adr0003_c35_owned_tables_scoped import app_sources
from tests.support import ownership_checks as oc

# Adding an entry is a gate-1 decision of the task that adds it (ADR-0003 addendum of EKO-3-08).
SYSTEM_READS = frozenset({"backend/app/data/staff.py:delete_unreferenced_copies"})
LISTED_PATH, LISTED_NAME = "backend/app/data/staff.py", "delete_unreferenced_copies"


def test_c35_the_list_in_the_check_is_the_list_held_here() -> None:
    assert oc.SYSTEM_READS == SYSTEM_READS


def test_c35_the_listed_function_exists_and_reaches_an_owned_table() -> None:
    assert f"{LISTED_PATH}:{LISTED_NAME}" in oc.owned_functions(app_sources())


def test_c35_the_repository_passes_the_restated_check() -> None:
    sources = app_sources()
    assert oc.unscoped_functions(sources) == []
    assert oc.system_read_problems(sources) == []


def test_c35_contrast_without_the_list_the_listed_function_is_unscoped() -> None:
    found = oc.unscoped_functions(app_sources(), system_reads=frozenset())
    assert found == [f"{LISTED_PATH}:{LISTED_NAME}: no scope parameter"]


LISTED_OK = """
from app.data.models import CustomerRow, StaffDisplayNameRow

REFERENCE_SET = (CustomerRow.owner_subject,)


def delete_unreferenced_copies(database, before):
    referred = or_(*(exists().where(c == StaffDisplayNameRow.subject) for c in REFERENCE_SET))
    with _connection(database) as connection:
        deleted = connection.execute(delete(StaffDisplayNameRow).where(not_(referred))).rowcount
    return int(deleted or 0)
"""

RETURNING = {
    "selects-an-owned-column": """
from app.data.models import CustomerRow


def delete_unreferenced_copies(database, before):
    rows = connection.execute(select(CustomerRow.owner_subject)).all()
    return 0
""",
    "returns-an-owned-column": """
from app.data.models import CustomerRow


def delete_unreferenced_copies(database, before):
    return CustomerRow.name
""",
    "returning-clause": """
from app.data.models import CustomerRow, StaffDisplayNameRow


def delete_unreferenced_copies(database, before):
    statement = delete(StaffDisplayNameRow).returning(CustomerRow.owner_subject)
    return connection.execute(statement).all()
""",
    "through-a-module-tuple": """
from app.data.models import CustomerRow

COLUMNS = (CustomerRow.owner_subject,)


def delete_unreferenced_copies(database, before):
    return connection.execute(select(*COLUMNS)).all()
""",
    "raw-sql": """
def delete_unreferenced_copies(database, before):
    connection.execute(text("DELETE FROM staff_display_name WHERE subject IN "
                            "(SELECT owner_subject FROM customer)"))
    return 0
""",
}


def test_c35_contrast_a_listed_function_returning_no_owned_column_passes() -> None:
    assert oc.system_read_problems({LISTED_PATH: LISTED_OK}) == []


@pytest.mark.parametrize("variant", sorted(RETURNING))
def test_c35_contrast_a_listed_function_returning_an_owned_column_fails(variant: str) -> None:
    problems = oc.system_read_problems({LISTED_PATH: RETURNING[variant]})
    assert problems and all(LISTED_NAME in p for p in problems), problems


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("backend/app/api/planted.py", f"from app.data.staff import {LISTED_NAME}\n"),
        ("backend/app/auth/planted.py", f"from app.data.staff import {LISTED_NAME} as sweep\n"),
        ("backend/app/api/planted.py", f"from app.data import staff\nstaff.{LISTED_NAME}(db, t)\n"),
        ("backend/app/auth/planted.py", "from app.services.retention import sweep\n"),
        ("backend/app/api/planted.py", "import app.services.retention\n"),
    ],
)
def test_c35_contrast_a_listed_function_reached_from_api_or_auth_fails(
    path: str, source: str
) -> None:
    files = {**app_sources(), path: source}
    assert any(path in p for p in oc.system_read_problems(files)), oc.system_read_problems(files)


def test_c35_contrast_the_same_import_in_services_passes() -> None:
    files = {
        **app_sources(),
        "backend/app/services/planted.py": f"from app.data.staff import {LISTED_NAME}\n",
    }
    assert oc.system_read_problems(files) == []


def test_c35_contrast_api_importing_the_listed_module_for_another_function_passes() -> None:
    files = {
        **app_sources(),
        "backend/app/api/planted.py": "from app.data.staff import StaffStore\n",
    }
    assert oc.system_read_problems(files) == []
