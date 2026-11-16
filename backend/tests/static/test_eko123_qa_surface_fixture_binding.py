"""EKO-1-23 QA (K-02, claim 1): the route/OpenAPI claim, run through its own pytest fixtures, stays
green when the live change set adds an endpoint.

`test_eko123_eko113_claims.py` hands the original test body a pair it computed itself, so the
fixture that binds the claim to PR #81's parents (`surfaces`) is never exercised there: putting the
old live reading back into that fixture survived every new test. Here the original fixtures
(`surfaces`, `live_surface`) are resolved by pytest inside a live state that holds a new endpoint:
a throwaway repository (tests/support/fixed_pair.py) whose HEAD is PR #81's head plus one route,
`CHANGESET_BASE` set to a later main commit, the way the CI job sets it. A second case hands the
pair reader that planted commit as its head (the reader must compare base with head, not with
itself). The real repository is never written (`real_repository_untouched`).
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.static import test_adr0005_eko113_changeset as claim
from tests.static.test_adr0005_eko113_changeset import live_surface, surfaces
from tests.support.fixed_pair import Throwaway, edit

# Re-exported so pytest resolves the original fixtures in this module, after the live state.
__all__ = ["live_surface", "surfaces"]

PAIR_HEAD = "947ff40efac06b13d6df48b6650024503f2e7308"
LATER_MAIN = "146057a88b2ed2db658261690a5b420f7dfa2f8d"
MAIN = "backend/app/main.py"
INCLUDE = '        app.include_router(health_router, prefix="/api")\n'
PLANTED = f'{INCLUDE}        app.add_api_route("/api/planted", lambda: {{}}, methods=["GET"])\n'

Surface = dict[str, Any]


@pytest.fixture(scope="module", autouse=True)
def live_tree_with_a_new_endpoint(
    tmp_path_factory: pytest.TempPathFactory, real_repository_untouched: None
) -> Iterator[str]:
    """Selected before the original module-scoped fixtures are built, and undone after them."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CHANGESET_BASE", LATER_MAIN)
        repo = Throwaway(tmp_path_factory.mktemp("live") / "repo", PAIR_HEAD, patch)
        planted = repo.commit(PAIR_HEAD, edit(MAIN, INCLUDE, PLANTED))
        repo.checkout_files(planted, "backend/app", "backend/migrations")
        patch.setattr(claim, "REPO_ROOT", repo.work)
        yield planted


def test_eko123_qa_surface_claim_through_its_fixtures_ignores_a_live_new_endpoint(
    surfaces: tuple[Surface, Surface], live_surface: Surface
) -> None:
    assert "GET /api/planted" in live_surface["routes"], "precondition: the live head has the plant"
    claim.test_adr0005_eko113_changeset_route_table_openapi_and_health_body(surfaces, live_surface)


def test_eko123_qa_surface_pair_reads_the_head_it_is_given(
    live_tree_with_a_new_endpoint: str, tmp_path: Path
) -> None:
    """K-03 binding through the pair reader: the same pair with only its head replaced by the
    planted commit is red, so the reader compares the base with the head, not with itself."""
    base, head = claim.pair_surfaces(tmp_path, head=live_tree_with_a_new_endpoint)
    assert "routes differs from the base branch's" in claim.surface_problems(base, head)
    assert "GET /api/planted" in head["routes"], "the head read is the planted one"
