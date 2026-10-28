"""Contrast for the C28 catalog reader (QA, EKO-1-06 fix round 1).

Two C28 tests now prove that a failed first initialisation created neither database by reading
the volume's catalog with `databases_on_volume` (the plain image, outside the composition). An
empty answer from that reader would pass them whatever the volume holds. Here the same reader on a
volume whose first initialisation succeeded, with only the passwords differing, must find both
databases.
"""

import pytest

from tests.runtime.conftest import Composition
from tests.runtime.test_k04_c28_failed_first_init import databases_on_volume

pytestmark = pytest.mark.runtime


def test_k04_c28_catalog_reader_finds_both_databases_on_a_completed_volume(
    fresh: Composition,
) -> None:
    fresh.compose("up", "-d", "--wait", "postgres", timeout=300)
    fresh.compose("stop", "postgres")
    found = databases_on_volume(f"{fresh.project}_pgdata", fresh.env["POSTGRES_PASSWORD"])
    assert {"eko", "keycloak"} <= found
