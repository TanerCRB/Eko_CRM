# EKO-1-40 evidence (#228)

Local evidence for EKO-1-40, from one Windows host (`DESKTOP-B7OHL9E`), recorded on 2026-11-22.
Nothing here was measured on the CI runners, and nothing here claims production behaviour.
Every value is synthetic.

**Branch reached: (a), then G-1.** The cause is confirmed under a controlled delay (K-01). The
best test-only send schedules found survive the delay only below the magnitude the real reds
show, and the structure of the carrier bounds any schedule. So no test-only change removes the
dependency without loosening a guarded bound (G-1 A: an accepted limit, recorded by the human).
The carrier file is unchanged.

| File | What it holds |
|---|---|
| [`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md) | K-01: the named test 30 of 30, M-1 seen failing, contrasts (1) and (2), the delay magnitudes |
| [`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md) | K-01's real undelayed loaded reds with S, their records, the loaded `find` durations (K-07) |
| [`fix-attempts-2026-11-22.md`](fix-attempts-2026-11-22.md) | K-03 / G-1: the two send schedules tried and why no schedule removes the dependency |

## Findings for the Issue

1. **S is reproduced by checkout latency on the holder's process.** With every checkout of the
   holder's process keeping its connection 0.2 s longer once the lock is held, the carrier body as
   it is at `b099acc` shows S in 30 of 30 runs of the named test (on-time, one-late, holder forced
   onto b) and in 36 of 36 recorded runs at 0.2 s. Without the delay, 29 of 30 runs had no S.
2. **It is not only the single free connection.** With the same delay on the non-holder process
   only (two free connections), S is absent, but every run went red with a 503 from `find` on
   that process (10 of 10). One real loaded red also had three such 503s on the non-holder
   process. The precise cause: checkout latency against the waiters' probes (every 0.1 s plus
   their own checkout), on a pool of 2 with overflow 0, makes a `find` (not retried) wait past
   the 0.5-s `POOL_TIMEOUT_SECONDS` before any blocker is placed. The holder's process, with one
   free connection, is the more exposed process, and S is its form of the failure.
3. **Real undelayed reds carry S.** Four real reds were recorded: three under an added busy-loop
   load and one in a host latency spike with no load added. All four show S, and two of them also
   show 503s on the non-holder process. No real red without S was recorded.
4. **No test-only fix.** Sending the holder's process's other requests one at a time (G-A A)
   passes at a delay of 0.05 and 0.1 s, but at 0.2 s it runs out of the guarded 2.0-s refresh
   window, with no 503. The carrier needs eight non-retried checkouts on one connection, plus the
   probes, inside that window. So any schedule fails at delays of about 0.15 – 0.2 s, and the real
   reds show checkouts of that order and above.

## K-07 side by side

| Quantity | Value | Source |
|---|---|---|
| Delay magnitude of K-01 | 0.2 s per checkout of the holder's process, once its lock is held (S from 0.1 s up; 1 of 6 at 0.05 s) | [`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md) |
| Real undelayed loaded `find` durations, red runs (4) | holder's process 0.062 – 1.187 s ok and 0.500 – 0.516 s unavailable; other process 0.094 – 1.141 s ok and 0.500 – 0.594 s unavailable | [`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md) |
| Real undelayed loaded `find` durations, green runs (19) | holder's process 0.000 – 0.281 s; other process 0.000 – 0.203 s | same |
| `find` durations under the K-01 delay (holder's process) | 0.000 – 0.703 s ok (the 85 delayed ones 0.218 s or more), 0.500 – 0.516 s unavailable | [`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md) |
| Load parameters | `load.py 24 330` (24 Python busy loops for 330 s) and `load.py 32 420`, started 3 s before pytest; Docker-VM busy loops dropped because they broke the throwaway PostgreSQL's setup | [`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md) |
| Rate of S in the real loop of #188 | 5 of 9 | #188, developer report of 2026-11-21 |
| Rate of S under the recorded load at `b099acc` | 2 of 12 (24 loops) and 1 of 10 (32 loops), in single-carrier runs, every one in the first one or two runs of a pytest session | [`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md) |
| Rate of S at `b099acc` with no load added | 1 of 30 (a host latency spike) | [`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md) |

Limits of this comparison:

- A real `find` duration includes the wait for a connection. The delay adds the hold of one
  checkout. The two are of the same order (tenths of a second), not the same quantity.
- The busy-loop load did not reproduce #188's 5-of-9 rate: under it, S came only at the start of
  a pytest session. The K-04 loop (the 20-iteration loop of EKO-1-33's K-06(a) under one recorded
  load, at a fix and at `b099acc`) was **not run**, because G-1 leaves no fix to run it at.

## The harness

The recorded runs, but not the named test, came from a temporary pytest module,
`backend/tests/runtime/eko201/test_zz_eko140_explore.py`. It was deleted before handoff and is
not in the tree. It called the carrier's own functions, kept both processes' `/__eko201/state`
when `all_waiting` failed, and appended one JSON line per run to a file outside the repository.
The tables were made from those lines with `backend/tests/support/eko140_signature.py`. The
module's last version is reproduced here so the runs can be repeated:

<details><summary>test_zz_eko140_explore.py (temporary, not in the tree)</summary>

```python
"""TEMPORARY exploration harness for EKO-1-40; deleted before handoff."""

import json
import os
import time
from typing import Any

import pytest

from tests.runtime.eko201 import test_eko201_k04_refresh_concurrency as k04
from tests.support import oidc_stub
from tests.support.eko140_signature import signature_s
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

N = int(os.environ.get("EXPLORE_N", "1"))
FACTORY = os.environ.get("EXPLORE_FACTORY", k04.OBSERVED)
FACTORIES = os.environ.get("EXPLORE_FACTORIES", FACTORY).split(",")
DELAYS = os.environ.get("EXPLORE_DELAYS", "-").split(",")
OUT = os.environ.get("EXPLORE_OUT", "")
LATE = os.environ.get("EXPLORE_LATE", "both")
LATES = {"both": [None, k04.LATE_SECONDS], "none": [None], "late": [k04.LATE_SECONDS]}[LATE]


@pytest.mark.parametrize("delay", DELAYS)
@pytest.mark.parametrize("factory", FACTORIES, ids=lambda f: f.rsplit(":", 1)[1])
@pytest.mark.parametrize("late", LATES, ids=lambda v: "on-time" if v is None else "one-late")
@pytest.mark.parametrize("i", range(N))
def test_explore(
    pg: Postgres, stub: oidc_stub.Stub, late: float | None, i: int, factory: str, delay: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if delay != "-":
        monkeypatch.setenv("EKO140_DELAY_SECONDS", delay)
    records: dict[str, Any] = {}

    def settle(s: oidc_stub.Stub, sid: str, a: k04.Backend, b: k04.Backend) -> Any:
        try:
            return k04.all_waiting(s, sid, a, b)
        except AssertionError:
            records.update(a=k04.observed(a), b=k04.observed(b))
            raise

    error = None
    run = None
    try:
        run = k04.pool_exhausted_responsive(pg, stub, settle, late, factory)
    except AssertionError as exc:
        error = str(exc)[:300]
    if run is not None:
        records = run.final
    statuses = None if run is None else [o.status for o in run.outcomes]
    hits = signature_s(records) if records else []
    line = {
        "at": time.time(), "i": i, "late": late, "factory": factory, "error": error,
        "statuses": statuses, "s": hits, "record": records,
        "marks": None if run is None else run.marks,
    }
    if OUT:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    print(f"EXPLORE i={i} late={late} error={'yes' if error else 'no'} statuses={statuses} S={len(hits)}")  # noqa: T201


GATED_N = int(os.environ.get("EXPLORE_GATED_N", "0"))
PIPELINED = os.environ.get("EXPLORE_PIPELINED") == "1"


@pytest.mark.parametrize("delay", DELAYS)
@pytest.mark.parametrize("i", range(GATED_N))
def test_explore_gated(
    pg: Postgres, stub: oidc_stub.Stub, i: int, monkeypatch: pytest.MonkeyPatch, delay: str
) -> None:
    if delay != "-":
        monkeypatch.setenv("EKO140_DELAY_SECONDS", delay)
    """Candidate F1: request 0 alone first; once its refresh reached the stub, the other process's
    requests at once and the holder process's others one at a time, each after the previous waits."""
    import threading

    send = k04.send_tagged
    turn = threading.Lock()

    def gated(target: k04.Backend, session: str, tag: int, at: oidc_stub.Stub,
              late: float | None, sends_started: float | None = None) -> k04.Outcome:
        if tag == 0:
            return send(target, session, tag, at, None)
        k04.wait_for_refresh(at)
        if tag % 2 == 1:
            return send(target, session, tag, at, None)
        with turn:
            result: list[k04.Outcome] = []
            t = threading.Thread(target=lambda: result.append(send(target, session, tag, at, None)))
            t.start()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                r = k04.observed(target)["requests"].get(str(tag))
                if r is not None and r["phase"] != "arrived" or r is not None and "status" in r:
                    break
                if PIPELINED and r is not None and any("ended" in c for c in r["checkouts"]):
                    break
                time.sleep(0.01)
        t.join()
        return result[0]

    monkeypatch.setattr(k04, "send_tagged", gated)
    records: dict[str, Any] = {}

    def settle(s: oidc_stub.Stub, sid: str, a: k04.Backend, b: k04.Backend) -> Any:
        try:
            return k04.all_waiting(s, sid, a, b)
        except AssertionError:
            records.update(a=k04.observed(a), b=k04.observed(b))
            raise

    error = None
    run = None
    try:
        run = k04.pool_exhausted_responsive(pg, stub, settle, None, FACTORY)
    except AssertionError as exc:
        error = str(exc)[:300]
    if run is not None:
        records = run.final
        try:
            assert [o.status for o in run.outcomes] == [200] * 10
            assert run.refresh_at_block == [None]
        except AssertionError as exc:
            error = "post: " + str(exc)[:200]
    statuses = None if run is None else [o.status for o in run.outcomes]
    hits = signature_s(records) if records else []
    line = {"at": time.time(), "i": i, "late": None, "factory": FACTORY, "error": error,
            "statuses": statuses, "s": hits, "record": records, "schedule": "pipelined" if PIPELINED else "gated",
            "marks": None if run is None else run.marks}
    if OUT:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
```

</details>

<details><summary>load.py (the load generator, run from outside the repository)</summary>

```python
"""CPU load generator for EKO-1-40 evidence: N busy-loop processes for T seconds (synthetic)."""
import multiprocessing, sys, time

def spin(until: float) -> None:
    x = 0
    while time.time() < until:
        x = (x * 31 + 7) % 1000003

if __name__ == "__main__":
    n, seconds = int(sys.argv[1]), float(sys.argv[2])
    until = time.time() + seconds
    procs = [multiprocessing.Process(target=spin, args=(until,)) for _ in range(n)]
    for p in procs: p.start()
    for p in procs: p.join()
```

</details>
