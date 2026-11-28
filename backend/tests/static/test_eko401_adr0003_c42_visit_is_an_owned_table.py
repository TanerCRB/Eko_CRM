"""EKO-4-01, ADR-0003-C42 static half (the accepted addendum, section 1; ADR-0003-C35, C36): the
visit table is an owned table of the C35 check, so every `data` function reading or writing it
takes a required, typed scope and no module outside `backend/app/data/` names it; and the scopes
the visit operations use are built only in `backend/app/domain/ownership.py`. The behavioural halves
are K-01 and K-02 under `tests/runtime/eko401/`.
"""

from tests.static.test_eko301_adr0003_c35_owned_tables_scoped import app_sources
from tests.support import ownership_checks as oc

VISITS = "backend/app/data/visits.py"


def test_k01_c42_the_visit_table_and_model_are_owned() -> None:
    assert "visit" in oc.OWNED_TABLES
    assert "VisitRow" in oc.OWNED_MODELS


def test_k01_c42_every_visit_store_function_takes_a_required_scope() -> None:
    sources = app_sources()
    reached = {name for name in oc.owned_functions(sources) if name.startswith(VISITS)}
    # Non-vacuity: the visit store's create, read and list reach the table.
    assert {f"{VISITS}:{name}" for name in ("create", "find", "find_all")} <= reached, reached
    assert oc.unscoped_functions(sources) == []
    assert oc.outside_references(sources) == []
    assert oc.scope_constructions(sources) == []


def test_k01_c42_contrast_an_unscoped_visit_read_is_found() -> None:
    planted = {
        "backend/app/data/planted.py": (
            "from app.data.models import VisitRow\n\n\n"
            "def every_visit(connection):\n"
            "    return connection.execute(select(VisitRow))\n"
        ),
        "backend/app/services/planted.py": 'QUERY = "SELECT id FROM visit"\n',
    }
    assert oc.unscoped_functions(planted) == [
        "backend/app/data/planted.py:every_visit: no scope parameter"
    ]
    assert oc.outside_references(planted) == ["backend/app/services/planted.py:1"]
