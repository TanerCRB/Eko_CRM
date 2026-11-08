"""K-06 (EKO-1-20, ADR-0004-C32): the accepted ADR-0004 addendum of 2026-11-08 and the shipped
backup script state the same bound on the control session's lock waits, and it is a limit.

The value is read from both texts, never written here as the expected one alone: a change to
either side only is a mismatch. PostgreSQL reads `0` as no limit, so a bound of 0 or below is
refused like a mismatch. That the addendum limits the bound to after the advisory lock is the
gate-1 decision itself, not something this test decides.
"""

import re

import pytest

from tests.support.repo import REPO_ROOT

SCRIPT = REPO_ROOT / "backup" / "eko-backup"
ADR = REPO_ROOT / "docs" / "architecture" / "decisions" / "ADR-0004-deployment-and-recovery.md"
ADDENDUM = (
    "### 2026-11-08 — The backup control session's lock wait after the advisory lock is granted"
)
# The value the human chose (Issue #76, C-1).
CHOSEN_SECONDS = 180.0
SCRIPT_BOUND = re.compile(r"lock_timeout\s*=\s*'(-?[0-9]+)\s*(ms|s|min)?'")
# PostgreSQL reads a lock_timeout with no unit as milliseconds.
UNIT_SECONDS = {"": 0.001, "ms": 0.001, "s": 1.0, "min": 60.0}
ADR_BOUND = re.compile(r"each wait for a lock ends after at\s+most\s+\*\*(-?[0-9]+) seconds\*\*")


def script_bounds(script: str) -> list[float]:
    return [int(value) * UNIT_SECONDS[unit] for value, unit in SCRIPT_BOUND.findall(script)]


def adr_bounds(adr: str) -> list[float]:
    start = adr.find(ADDENDUM)
    if start < 0:
        return []
    following = adr.find("\n### ", start + len(ADDENDUM))
    section = adr[start:] if following < 0 else adr[start:following]
    return [float(value) for value in ADR_BOUND.findall(section)]


def bound_problems(script: str, adr: str) -> list[str]:
    in_script, in_adr = script_bounds(script), adr_bounds(adr)
    if len(in_script) != 1:
        return [f"backup/eko-backup states the control bound {len(in_script)} times, not once"]
    if len(in_adr) != 1:
        return [f"the 2026-11-08 addendum states the control bound {len(in_adr)} times, not once"]
    problems = [
        f"{place} states {value:g} s, which PostgreSQL reads as no limit"
        for place, value in (("backup/eko-backup", in_script[0]), ("ADR-0004", in_adr[0]))
        if value <= 0
    ]
    if in_script[0] != in_adr[0]:
        problems.append(f"backup/eko-backup states {in_script[0]:g} s, ADR-0004 {in_adr[0]:g} s")
    return problems


def test_eko120_k06_adr_and_script_state_the_same_control_bound() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")
    assert bound_problems(script, adr) == []
    assert script_bounds(script) == adr_bounds(adr) == [CHOSEN_SECONDS]


@pytest.mark.parametrize("planted", ["179s", "0", "0s", "-1s"])
def test_eko120_k06_contrast_a_script_value_changed_alone_is_reported(planted: str) -> None:
    shipped = SCRIPT.read_text(encoding="utf-8")
    script = SCRIPT_BOUND.sub(f"lock_timeout = '{planted}'", shipped)
    assert script != shipped, "the shipped script states no control bound to change"
    assert bound_problems(script, ADR.read_text(encoding="utf-8")) != []


def test_eko120_k06_contrast_a_script_with_no_bound_or_two_is_reported() -> None:
    shipped = SCRIPT.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")
    assert bound_problems(SCRIPT_BOUND.sub("", shipped), adr) != []
    assert bound_problems(shipped + "\n# lock_timeout = '180s'\n", adr) != []


def test_eko120_k06_contrast_the_adr_value_changed_alone_is_reported() -> None:
    adr = ADR.read_text(encoding="utf-8")
    planted = re.sub(r"(at\s+most\s+\*\*)180( seconds\*\*)", r"\g<1>240\2", adr)
    assert planted != adr, "the addendum's wording moved; update the planted contrast"
    assert bound_problems(SCRIPT.read_text(encoding="utf-8"), planted) != []
