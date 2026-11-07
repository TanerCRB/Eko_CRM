"""EKO-1-15 K-06 / ADR-0004-C13, previous-release half (G-2 A): the previous published release's
`migrate` and `backend`, by digest, against a database at the next release's head.

The previous release is selected as the API-compatibility step selects it
(tests/support/releases.py): the newest published release reachable from `main`, other than the
one being built (RELEASE_TAG). With none, this half compared nothing and is skipped, never passed;
when the record or reachability cannot be read, it fails. It needs the record token
(RELEASE_RECORD_TOKEN), a registry login and the full history, so it carries its own marker and
runs where those are granted (the release workflow's runtime job).
"""

import json
import os

import pytest

from tests.runtime.lab import Lab, docker, health_body
from tests.support.releases import (
    CannotTell,
    c13_previous_backend,
    reach_from_environment,
    record_from_environment,
)

pytestmark = pytest.mark.previous_release


@pytest.fixture(scope="module")
def previous_backend() -> str:
    try:
        found = c13_previous_backend(
            record_from_environment(), reach_from_environment(), os.environ.get("RELEASE_TAG")
        )
    except CannotTell as error:
        pytest.fail(f"C13 previous-release half: the check itself failed: {error}")
    if found is None:
        pytest.skip(
            "no published release is reachable from main: C13's previous-release half "
            "compared nothing and reports no pass"
        )
    docker("pull", "--quiet", found, timeout=600)
    return found


def test_eko115_k06_c13_previous_release_on_the_next_head(lab: Lab, previous_backend: str) -> None:
    lab.at_variant_head("next")
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(previous_backend)
    assert code == 0, logs
    assert lab.comparison_dump() == before
    previous = lab._with_image("backend", previous_backend)
    previous.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
    lab.wait_for_health("200", 90)
    assert json.loads(health_body(lab)) == {"status": "ok"}
    assert lab.comparison_dump() == before
