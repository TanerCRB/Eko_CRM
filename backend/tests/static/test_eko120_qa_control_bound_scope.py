"""QA, EKO-1-20 (ADR-0004 addendum 2026-11-08, *The bound*: "set as a transaction-local
setting"): the control session's lock bound lasts only for the snapshot transaction.

K-06 checks the value the script and the addendum state, not its scope, and no runtime test
can see the difference today: after the snapshot transaction's COMMIT the control session runs
only `pg_advisory_unlock`, which never waits. A session-level `SET lock_timeout` in the same
place would pass every runtime test and still be in force for any statement later added after
the commit (the addendum's P2 cost, "later control-session statement waits would inherit it
unnoticed"). This check reads the scope from the script.
"""

import re

from tests.support.repo import REPO_ROOT

SCRIPT = REPO_ROOT / "backup" / "eko-backup"
# A statement that sets lock_timeout in any form: SET [SESSION|LOCAL] ..., set_config(...).
SETS_LOCK_TIMEOUT = re.compile(
    r"\bSET\s+(?:(?P<scope>SESSION|LOCAL)\s+)?lock_timeout\b"
    r"|set_config\(\s*'lock_timeout'\s*,\s*'[^']*'\s*,\s*(?P<local>true|false)\s*\)",
    re.IGNORECASE,
)


def scope_problems(script: str) -> list[str]:
    found = list(SETS_LOCK_TIMEOUT.finditer(script))
    if len(found) != 1:
        return [f"backup/eko-backup sets lock_timeout {len(found)} times, not once"]
    [match] = found
    local = (match["scope"] or "").upper() == "LOCAL" or (match["local"] or "").lower() == "true"
    return [] if local else [f"the control bound is not transaction-local: {match[0]!r}"]


def test_eko120_qa_the_control_bound_is_transaction_local() -> None:
    assert scope_problems(SCRIPT.read_text(encoding="utf-8")) == []


def test_eko120_qa_contrast_a_session_level_bound_is_reported() -> None:
    shipped = SCRIPT.read_text(encoding="utf-8")
    for planted in ("SET lock_timeout", "SET SESSION lock_timeout"):
        script = shipped.replace("SET LOCAL lock_timeout", planted)
        assert script != shipped, "the shipped script states no SET LOCAL bound to change"
        assert scope_problems(script) != [], planted
