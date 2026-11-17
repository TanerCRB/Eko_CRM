"""EKO-1-33 K-03 (ADR-0003, "no request is served on an expired access token"): the login callback
refuses a token at its expiry instant, with no leeway; one second earlier it logs in.

In-process on the shared `FakeClock`, because the boundary instant must be exact: the stub mints
at a fixed instant and the application's clock is set relative to it.
"""

from datetime import timedelta
from typing import Any

import pytest

from tests.runtime.eko201.conftest import (
    SESSION_COOKIE,
    AppFactory,
    FakeClock,
    refused_at_callback,
    session_count,
    set_cookies,
)
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

LIFESPAN = 60

# (tokens expiring at the callback's instant, seconds from minting to the callback)
CASES = {
    "both-at-expiry": ("both", LIFESPAN),
    "contrast-both-one-second-before": ("none", LIFESPAN - 1),
    "access-only-at-expiry": ("access", LIFESPAN),
    "id-only-at-expiry": ("id", LIFESPAN),
}


@pytest.mark.parametrize("case", list(CASES))
def test_eko133_k03_callback_refuses_a_token_at_its_expiry_instant(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    clock: FakeClock,
    pg: Postgres,
    case: str,
) -> None:
    expiring, seconds = CASES[case]
    minted = clock.at
    stub.now = lambda: minted
    at_callback = int((minted + timedelta(seconds=seconds)).timestamp())
    if expiring in ("access", "id"):
        # The other token lives one second past the callback's instant.
        stub.access_lifespan_seconds = LIFESPAN + 1
        overrides = stub.access_overrides if expiring == "access" else stub.id_overrides
        overrides["exp"] = at_callback
    else:
        stub.access_lifespan_seconds = LIFESPAN
    browser = browser_for(make_app())
    path = browser.at_identity_server(browser.start_login())
    clock.at = minted + timedelta(seconds=seconds)
    answer = browser.send("GET", path)
    session_cookies = [c for c in set_cookies(answer) if c.name == SESSION_COOKIE and not c.cleared]
    if expiring == "none":
        assert answer.status_code == 303, answer.text
        assert not refused_at_callback(answer), answer.headers
        assert len(session_cookies) == 1
        assert session_count(pg) == 1
    else:
        assert refused_at_callback(answer), answer.headers
        assert session_cookies == []
        assert session_count(pg) == 0
