"""Signature S of EKO-1-40 (#228), read from the server-side record of a pool-exhausted run.

A record is `{"a": state, "b": state}`, each state what `/__eko201/state` answered. S is a tagged
request on the holder's process (the process with a request in phase `holding` or `held`) whose
only checkout is a `find` that ended `unavailable` at least `S_MIN_SECONDS` after it started, that
answered 503, on a process whose blockers were not placed before that `find` ended.
"""

from typing import Any

# Fits the 0.5-s `POOL_TIMEOUT_SECONDS` and the "about 0.515 s" observed in #188 / #228.
S_MIN_SECONDS = 0.45


def holder_process(record: dict[str, dict[str, Any]]) -> str | None:
    found = [
        name
        for name, state in record.items()
        if any(r["phase"] in ("holding", "held") for r in state["requests"].values())
    ]
    return found[0] if len(found) == 1 else None


def signature_s(record: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every request of the record that shows S, with its process and tag; empty without S."""
    holder = holder_process(record)
    if holder is None:
        return []
    state = record[holder]
    held_at = state["held_at"]
    hits = []
    for tag, request in state["requests"].items():
        checkouts = request["checkouts"]
        if len(checkouts) != 1:
            continue
        [find] = checkouts
        if find["step"] != "find" or find.get("outcome") != "unavailable":
            continue
        if find["ended"] - find["started"] < S_MIN_SECONDS or request.get("status") != 503:
            continue
        if held_at is not None and held_at <= find["ended"]:
            continue
        hits.append({"process": holder, "tag": tag, "find": find, "status": request["status"]})
    return hits
