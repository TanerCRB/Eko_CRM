"""EKO-1-33 QA: contrasts the developer's carriers do not hold.

K-04 contrast: the carriers' premise (the first request on a short-lived login finds the access
token expired and refreshes) is separated from a default-lifespan login by the lifespan alone; the
wait before the first request is the same in both cases.

K-05(b) contrast: a login the callback refuses once must surface as a refusal through the shared
harness (`processes.expired_login`) after exactly one code exchange. The K-02 carrier cannot show
this: its controlled interval refuses every attempt at the pre-fix tree and none at the fixed tree,
so a retry around the callback never changes its outcome. A refusal on the first exchange only is
the case a retry would hide.
"""

import time
from typing import Any

import pytest

from tests.runtime.eko201.conftest import session_count
from tests.runtime.eko201.processes import (
    LONG_LIFESPAN_SECONDS,
    SHORT_LIFESPAN_SECONDS,
    access_expiry,
    backend,
    expired_login,
    login,
)
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime


def code_exchanges(stub: oidc_stub.Stub) -> int:
    with stub.lock:
        return len([c for c in stub.token_calls if c.grant_type == "authorization_code"])


@pytest.mark.parametrize(
    "lifespan",
    [SHORT_LIFESPAN_SECONDS, LONG_LIFESPAN_SECONDS],
    ids=["short-lived", "contrast-default-lifespan"],
)
def test_eko133_qa_k04_first_request_refreshes_only_a_login_whose_token_has_expired(
    pg: Postgres, stub: oidc_stub.Stub, lifespan: int
) -> None:
    with backend(pg, stub) as a:
        first = len(stub.issued)
        stub.access_lifespan_seconds = lifespan
        try:
            session = login(a)
        finally:
            stub.access_lifespan_seconds = LONG_LIFESPAN_SECONDS
        [expiry] = [e for e in map(access_expiry, stub.issued[first:]) if e is not None]
        # The same wait in both cases: until a short-lived token minted at this instant expired.
        until = expiry - lifespan + SHORT_LIFESPAN_SECONDS
        while time.time() <= until:
            time.sleep(0.05)
        premise = time.time() > expiry
        status = a.get("/api/auth/session", session).status_code
        refreshes = len(stub.refreshes())
    assert status == 200
    if lifespan == SHORT_LIFESPAN_SECONDS:
        assert premise, (time.time(), expiry)
        assert refreshes == 1
    else:
        assert not premise, (time.time(), expiry)
        assert refreshes == 0


@pytest.mark.parametrize("refused_once", [True, False], ids=["refused-once", "contrast-accepted"])
def test_eko133_qa_k05_a_refused_login_surfaces_after_one_code_exchange(
    pg: Postgres, stub: oidc_stub.Stub, monkeypatch: pytest.MonkeyPatch, refused_once: bool
) -> None:
    mint = stub.mint
    held: list[str] = []

    def first_login_expired(user: oidc_stub.User, sid: str, nonce: str | None) -> dict[str, Any]:
        # Only the first login's exchange answers an access token already expired; the
        # callback's expiry check refuses it, any later exchange is the stub's default.
        if not refused_once or nonce is None or held:
            return mint(user, sid, nonce)
        held.append(sid)
        stub.access_overrides = {"exp": int(time.time()) - 1}
        try:
            return mint(user, sid, nonce)
        finally:
            stub.access_overrides = {}

    monkeypatch.setattr(stub, "mint", first_login_expired)
    with backend(pg, stub) as a:
        if refused_once:
            with pytest.raises(AssertionError, match="__Host-eko_session not set"):
                expired_login(stub, a)
        else:
            expired_login(stub, a)
    assert code_exchanges(stub) == 1
    assert session_count(pg) == (0 if refused_once else 1)
    assert stub.access_lifespan_seconds == LONG_LIFESPAN_SECONDS
