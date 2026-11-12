"""EKO-2-01 K-05 (ADR-0003-C28): killing the refresh holder's process releases its session-level
advisory lock, so a later refresh can start and the session does not answer 503 until logout.

The holder is the process whose request reached the identity server (or the pause point); it is
killed while its call is in flight. Release is observed in `pg_locks`, not inferred from the dead
request ending. The contrast holds the same lock from a connection that does not die.
"""

import contextlib
import time
from pathlib import Path

import httpx
import pytest

from tests.runtime.eko201.conftest import session_count
from tests.runtime.eko201.processes import backend, login
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

PAUSE = "tests.support.eko201_fixture_app:create_with_pause"


def advisory_locks(pg: Postgres) -> list[tuple[int, int]]:
    return [
        (int(classid), int(objid))
        for classid, objid in pg.rows(
            "SELECT classid::bigint, objid::bigint FROM pg_locks "
            "WHERE locktype = 'advisory' AND objsubid = 2 AND granted"
        )
    ]


def holder_states(pg: Postgres) -> list[str]:
    return [
        str(state)
        for (state,) in pg.rows(
            "SELECT a.state FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE l.locktype = 'advisory' AND l.objsubid = 2 AND l.granted"
        )
    ]


def wait_until(condition: object, seconds: float = 15) -> None:
    deadline = time.monotonic() + seconds
    while not condition():  # type: ignore[operator]
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def _expired(stub: oidc_stub.Stub, target: object) -> str:
    stub.access_lifespan_seconds = 1
    session = login(target)  # type: ignore[arg-type]
    stub.access_lifespan_seconds = 240
    time.sleep(1.3)
    return session


def _send_async(target: object, session: str) -> None:
    import threading

    threading.Thread(
        target=lambda: _quiet(target, session), daemon=True
    ).start()


def _quiet(target: object, session: str) -> None:
    with contextlib.suppress(httpx.HTTPError):
        # The request dies with its killed process.
        target.get("/api/auth/session", session, timeout=60)  # type: ignore[attr-defined]


@pytest.mark.parametrize("point", ["while_hanging", "before_send"])
def test_k05_holder_death_before_the_answer_releases_the_lock_and_refresh_recovers(
    pg: Postgres, stub: oidc_stub.Stub, tmp_path: Path, point: str
) -> None:
    marker = tmp_path / "paused"
    extra = {"EKO201_PAUSE": "before_send", "EKO201_MARKER": str(marker)}
    factory = PAUSE if point == "before_send" else "app.main:create_app"
    with backend(pg, stub) as survivor, backend(pg, stub, factory=factory, extra=extra) as holder:
        session = _expired(stub, survivor)
        if point == "while_hanging":
            stub.refresh_mode = "hang"
        _send_async(holder, session)
        if point == "while_hanging":
            wait_until(lambda: len(stub.refreshes()) == 1)
        else:
            wait_until(marker.exists)
        assert len(advisory_locks(pg)) == 1
        # The lock is held with no transaction open across the call (ADR-0003-C28, C16).
        assert holder_states(pg) == ["idle"]
        holder.kill()
        wait_until(lambda: advisory_locks(pg) == [])
        stub.refresh_mode = "answer"
        stub.release.set()
        answers = [survivor.get("/api/auth/session", session).status_code for _ in range(3)]
    assert answers == [200, 200, 200]
    assert session_count(pg) == 1
    expected = 2 if point == "while_hanging" else 1
    assert len(stub.refreshes()) == expected


def test_k05_holder_death_after_the_answer_keeps_the_rotation_consequence_not_the_lock(
    pg: Postgres, stub: oidc_stub.Stub, tmp_path: Path
) -> None:
    marker = tmp_path / "paused"
    extra = {"EKO201_PAUSE": "after_answer", "EKO201_MARKER": str(marker)}
    with backend(pg, stub) as survivor, backend(pg, stub, factory=PAUSE, extra=extra) as holder:
        session = _expired(stub, survivor)
        _send_async(holder, session)
        wait_until(marker.exists)
        holder.kill()
        wait_until(lambda: advisory_locks(pg) == [])
        # Keycloak rotated the refresh token the dead holder never stored: the next refresh is
        # refused and the session ends (ADR-0003 *Unreachable*), never a stranded 503.
        answers = [survivor.get("/api/auth/session", session).status_code for _ in range(2)]
    assert answers == [401, 401]
    assert session_count(pg) == 0
    assert len(stub.superseded_uses()) == 1


def test_k05_contrast_lock_never_released_keeps_answering_503_until_the_session_is_deleted(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    with backend(pg, stub) as survivor:
        session = _expired(stub, survivor)
        from app.data.sessions import REFRESH_LOCK_CLASS

        [[row_id]] = pg.rows("SELECT id FROM app_session")
        with pg.connect() as stranded:
            stranded.execute(
                "SELECT pg_advisory_lock(%s::integer, %s::integer)",
                (REFRESH_LOCK_CLASS, int(row_id) % 2**31),
            )
            answers = [survivor.get("/api/auth/session", session).status_code for _ in range(2)]
            assert stub.refreshes() == []
            stranded.execute("DELETE FROM app_session")
            deleted = survivor.get("/api/auth/session", session).status_code
    assert answers == [503, 503]
    assert deleted == 401


def test_k05_an_unrelated_session_stays_usable_while_a_holder_hangs(
    pg: Postgres, stub: oidc_stub.Stub
) -> None:
    with backend(pg, stub) as a:
        stuck = _expired(stub, a)
        fine = login(a)
        stub.refresh_mode = "hang"
        _send_async(a, stuck)
        wait_until(lambda: len(stub.refreshes()) == 1)
        started = time.monotonic()
        assert a.get("/api/auth/session", fine).status_code == 200
        assert time.monotonic() - started < 1.0
        stub.release.set()
