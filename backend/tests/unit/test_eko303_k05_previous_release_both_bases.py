"""EKO-3-03 K-05 (4), both bases (the EKO-3-02 K-06 pattern): the previous-release test runs its
step while the previous release's head is 0004, fails when it is 0005 or 0006 (the gate-1
deviation lapsed), skips once it is 0007 or later, and fails on a release older than 0004 or on a
head that is not a numeric revision. Without every half, a skip or a pass could hide the lapse.

The decision is the `step` fixture of `tests/runtime/test_eko303_k05_previous_release_on_0007.py`,
called unwrapped with the image's head stubbed, so no image is pulled or run here. The fixture's
skip and fail are caught here, never let through.
"""

import inspect

import pytest

from tests.runtime import test_eko303_k05_previous_release_on_0007 as k05

IMAGE = "registry.example.invalid/eko-crm/backend@sha256:" + "0" * 64


def outcome(monkeypatch: pytest.MonkeyPatch, head: str) -> tuple[str, str]:
    monkeypatch.setattr(k05, "image_head", lambda image: head)
    try:
        decided = inspect.unwrap(k05.step)(IMAGE)
    except pytest.skip.Exception as skipped:
        return "skipped", str(skipped)
    except pytest.fail.Exception as failed:
        return "failed", str(failed)
    return "ran", str(decided)


def test_k05_on_a_previous_release_at_0004_the_step_runs_on_that_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (k05.PREVIOUS_HEAD, k05.REVISION) == ("0004", "0007")
    assert outcome(monkeypatch, "0004") == ("ran", IMAGE)


@pytest.mark.parametrize("head", ["0005", "0006"])
def test_k05_a_previous_release_at_0005_or_0006_fails_as_the_lapsed_deviation(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = outcome(monkeypatch, head)
    assert kind == "failed", reason
    assert f"head is {head}" in reason
    assert "lapsed" in reason


@pytest.mark.parametrize("head", ["0007", "0008", "0012"])
def test_k05_contrast_on_a_previous_release_at_0007_or_later_the_step_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = outcome(monkeypatch, head)
    assert kind == "skipped", reason
    assert f"head is {head}" in reason


@pytest.mark.parametrize("head", ["0003", "0001"])
def test_k05_a_previous_release_older_than_0004_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = outcome(monkeypatch, head)
    assert kind == "failed", reason
    assert "no customer operations" in reason


@pytest.mark.parametrize("head", ["ae1027a6acf", "base", "head", ""])
def test_k05_a_previous_release_with_a_non_numeric_head_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = outcome(monkeypatch, head)
    assert kind == "failed", reason
    assert f"head {head!r} is not a numeric revision" in reason
