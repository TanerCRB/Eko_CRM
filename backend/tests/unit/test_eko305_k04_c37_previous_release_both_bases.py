"""EKO-3-05 K-04, ADR-0004-C37, both bases (QA; the EKO-3-02 K-06 and EKO-3-03 K-05 pattern;
gate-1 decision D-3 W-1 A, exception EKO-3-05/weakening-1): the previous-release carrier over the
archived-state step runs while the previous release's head is 0004 up to 0007, skips once it is
0008 or later and names why, and fails on a release older than 0004, on a head that is not a
numeric revision, and when no previous release can be found. Without every half, a skip or a pass
could hide the step: a threshold left at 0007 (mutation EKO305-M-p10) would skip a release
published from `main` with EKO-3-03, the one release this carrier exists for.

The decision is the `previous_head` (and `previous_backend`) fixture of
`tests/runtime/test_eko305_k04_c37_previous_release_over_the_archived_state.py`, called unwrapped
with the image's head and the release record stubbed, so no image is pulled or run here. The
fixture's skip and fail are caught here, never let through.
"""

import inspect
from typing import Any

import pytest

from tests.runtime import test_eko305_k04_c37_previous_release_over_the_archived_state as c37
from tests.support.releases import CannotTell

IMAGE = "registry.example.invalid/eko-crm/backend@sha256:" + "0" * 64


def head_outcome(monkeypatch: pytest.MonkeyPatch, head: str) -> tuple[str, str]:
    monkeypatch.setattr(c37, "image_head", lambda image: head)
    try:
        decided = inspect.unwrap(c37.previous_head)(IMAGE)
    except pytest.skip.Exception as skipped:
        return "skipped", str(skipped)
    except pytest.fail.Exception as failed:
        return "failed", str(failed)
    return "ran", str(decided)


def backend_outcome(monkeypatch: pytest.MonkeyPatch, found: Any) -> tuple[str, str]:
    pulled: list[tuple[Any, ...]] = []
    monkeypatch.setattr(c37, "record_from_environment", lambda: "record")
    monkeypatch.setattr(c37, "reach_from_environment", lambda: "reach")
    monkeypatch.setattr(c37, "docker", lambda *args, **kwargs: pulled.append(args))

    def previous(record: Any, reach: Any, tag: Any) -> Any:
        if isinstance(found, Exception):
            raise found
        return found

    monkeypatch.setattr(c37, "c13_previous_backend", previous)
    try:
        decided = inspect.unwrap(c37.previous_backend)()
    except pytest.skip.Exception as skipped:
        return "skipped", str(skipped)
    except pytest.fail.Exception as failed:
        assert pulled == [], "nothing is pulled when no previous release is found"
        return "failed", str(failed)
    assert pulled == [("pull", "--quiet", found)]
    return "ran", str(decided)


def test_eko305_qa_k04_c37_thresholds_are_0004_and_0008() -> None:
    assert (c37.OLDEST_HEAD, c37.REVISION) == ("0004", "0008")


@pytest.mark.parametrize("head", ["0004", "0005", "0006", "0007"])
def test_eko305_qa_k04_c37_runs_on_a_previous_release_from_0004_to_0007(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    # 0004 is v0.1.2 today; 0007 is a release published from main with EKO-3-03 (K-04).
    assert head_outcome(monkeypatch, head) == ("ran", head)


@pytest.mark.parametrize("head", ["0008", "0009", "0012"])
def test_eko305_qa_k04_c37_contrast_skips_on_a_previous_release_at_0008_or_later(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = head_outcome(monkeypatch, head)
    assert kind == "skipped", reason
    assert f"head is {head}" in reason
    assert "the 0008 step is behind it" in reason


@pytest.mark.parametrize("head", ["0003", "0001"])
def test_eko305_qa_k04_c37_a_previous_release_older_than_0004_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = head_outcome(monkeypatch, head)
    assert kind == "failed", reason
    assert f"head is {head}, older than 0004" in reason


@pytest.mark.parametrize("head", ["ae1027a6acf", "base", "head", ""])
def test_eko305_qa_k04_c37_a_non_numeric_or_missing_head_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = head_outcome(monkeypatch, head)
    assert kind == "failed", reason
    assert f"head {head!r} is not a numeric revision" in reason


def test_eko305_qa_k04_c37_no_reachable_previous_release_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kind, reason = backend_outcome(monkeypatch, None)
    assert kind == "failed", reason
    assert "no published release is reachable" in reason


def test_eko305_qa_k04_c37_an_unreadable_release_record_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kind, reason = backend_outcome(monkeypatch, CannotTell("synthetic: record unreadable"))
    assert kind == "failed", reason
    assert "the previous release could not be read" in reason


def test_eko305_qa_k04_c37_contrast_a_found_release_is_pulled_and_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert backend_outcome(monkeypatch, IMAGE) == ("ran", IMAGE)
