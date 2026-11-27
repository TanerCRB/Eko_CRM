"""EKO-4-01 QA, K-01 (d) (ADR-0006 *Visit identifiers are never reused*; gate 1 A-1 A): the visit
identifier generator holds no state that a restarted server starts again from.

A server restored from a backup set is a fresh process. If the generator were seeded or counted in
the process (a fixed `random.Random` seed, a module counter), every fresh process would issue the
same identifiers again, those issued after the set included. The restore test
(`tests/runtime/test_eko401_k01_visit_identifiers_after_a_restore.py`) cannot see that: the
identifiers it compares against are planted by the test with `uuid.uuid4()`, not issued by the
application, and its own five identifiers come from the test's one process. Here two fresh
interpreters each ask the application's generator for identifiers, and none repeats.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
COUNT = 50
PROBE = (
    "from app.data.visits import new_identifier; "
    f"print(' '.join(str(new_identifier()) for _ in range({COUNT})))"  # leftovers-allow: probe
)
# The contrast: a generator seeded in the process, as a restarted server would run it.
SEEDED_PROBE = (
    "import random, uuid; r = random.Random(401); "
    "seeded = lambda: uuid.UUID(int=r.getrandbits(128), version=4); "
    f"print(' '.join(str(seeded()) for _ in range({COUNT})))"  # leftovers-allow: probe
)


def fresh_process(source: str) -> list[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    done = subprocess.run(
        [sys.executable, "-c", source],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return done.stdout.split()


def repeated(first: list[str], second: list[str]) -> set[str]:
    return set(first) & set(second)


def test_qa_k01_two_fresh_processes_issue_no_identifier_twice() -> None:
    first, second = fresh_process(PROBE), fresh_process(PROBE)
    assert len(first) == len(second) == COUNT
    assert len(set(first)) == COUNT
    assert repeated(first, second) == set()
    assert {uuid.UUID(identifier).version for identifier in first + second} == {4}


def test_qa_k01_contrast_a_generator_seeded_in_the_process_repeats_in_the_next_one() -> None:
    first, second = fresh_process(SEEDED_PROBE), fresh_process(SEEDED_PROBE)
    assert {uuid.UUID(identifier).version for identifier in first} == {4}
    assert repeated(first, second) == set(first)
