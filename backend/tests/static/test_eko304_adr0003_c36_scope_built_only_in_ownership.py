"""EKO-3-04, ADR-0003-C36 (addendum of EKO-3-04, Q-4 A): under `backend/app/`, an `OwnedBy` or
`AllRecords` value is constructed only in `backend/app/domain/ownership.py`, so a request value
never becomes a visibility scope. Run on the repository's sources and on planted fixtures, so the
check can fail.
"""

import pytest

from tests.static.test_eko301_adr0003_c35_owned_tables_scoped import app_sources
from tests.support import ownership_checks as oc

OWNERSHIP = "backend/app/domain/ownership.py"


def test_c36_scope_values_are_constructed_only_in_the_ownership_module() -> None:
    sources = app_sources()
    # Non-vacuity: the ownership module itself constructs both, and the check sees it.
    assert {path for path, _ in oc.scope_constructions(sources, everywhere=True)} == {OWNERSHIP}
    assert oc.scope_constructions(sources) == []


PLANTED = {
    "service-turns-the-filter-into-a-scope": (
        "backend/app/services/planted.py",
        """
from app.domain.ownership import OwnedBy


def list_for(store, caller, owner):
    return store.find_all(OwnedBy(owner))
""",
    ),
    "api-gives-every-record": (
        "backend/app/api/planted.py",
        """
from app.domain import ownership


def everything(store):
    return store.find_all(ownership.AllRecords())
""",
    ),
    "aliased-import": (
        "backend/app/services/planted.py",
        """
from app.domain.ownership import OwnedBy as Scope


def list_for(store, owner):
    return store.find_all(Scope(subject=owner))
""",
    ),
    "data-builds-its-own-scope": (
        "backend/app/data/planted.py",
        """
from app.domain.ownership import OwnedBy


def narrowed(scope, owner):
    return OwnedBy(owner)
""",
    ),
    "a-default-argument": (
        "backend/app/data/planted.py",
        """
from app.domain.ownership import AllRecords


def every(store, scope=AllRecords()):
    return store.find_all(scope)
""",
    ),
}


@pytest.mark.parametrize("variant", sorted(PLANTED))
def test_c36_contrast_a_scope_constructed_elsewhere_fails(variant: str) -> None:
    path, text = PLANTED[variant]
    assert [found for found, _ in oc.scope_constructions({path: text})] == [path]


def test_c36_contrast_the_same_construction_in_the_ownership_module_passes() -> None:
    _, text = PLANTED["service-turns-the-filter-into-a-scope"]
    assert oc.scope_constructions({OWNERSHIP: text}) == []


def test_c36_contrast_naming_a_scope_type_without_constructing_it_passes() -> None:
    text = """
from app.domain.ownership import AllRecords, OwnedBy, VisibilityScope


def visible(scope: VisibilityScope):
    return isinstance(scope, AllRecords) or isinstance(scope, OwnedBy)
"""
    assert oc.scope_constructions({"backend/app/data/planted.py": text}) == []


def test_c36_a_file_outside_backend_app_is_not_judged() -> None:
    _, text = PLANTED["service-turns-the-filter-into-a-scope"]
    assert oc.scope_constructions({"backend/tests/support/planted.py": text}) == []
