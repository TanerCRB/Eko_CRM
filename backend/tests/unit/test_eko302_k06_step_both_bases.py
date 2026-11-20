"""EKO-3-02 K-06, recorded exception `EKO-3-02/weakening-2` (A-09), both bases: the K-06 runtime
tests run their step while the previous release's head is 0004 and skip once a published release
already holds 0005 (the step then lies behind it); a release older than 0004 fails, as Q-2 B
requires. Without both halves the skip could hide K-06 on the very base it exists for.

The decision is the `step` fixture of `tests/runtime/test_eko302_k06_expand_on_customer.py`, called
unwrapped with the image's head stubbed, so no image is pulled or run here (QA, EKO-3-02). The
fixture's skip and fail are caught here, never let through: a skip escaping would skip this test
instead of failing it.
"""

import inspect

import pytest

from tests.runtime import test_eko302_k06_expand_on_customer as k06

IMAGE = "registry.example.invalid/eko-crm/backend@sha256:" + "0" * 64


def outcome(monkeypatch: pytest.MonkeyPatch, head: str) -> tuple[str, str]:
    """What the fixture does on a previous release whose head is `head`."""
    monkeypatch.setattr(k06, "image_head", lambda image: head)
    try:
        decided = inspect.unwrap(k06.step)(IMAGE)
    except pytest.skip.Exception as skipped:
        return "skipped", str(skipped)
    except pytest.fail.Exception as failed:
        return "failed", str(failed)
    return "ran", str(decided)


def test_k06_on_a_previous_release_at_0004_the_step_runs_on_that_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (k06.STEP_BASE, k06.HEAD) == ("0004", "0005")
    assert outcome(monkeypatch, "0004") == ("ran", IMAGE)


@pytest.mark.parametrize("head", ["0005", "0006"])
def test_k06_contrast_on_a_previous_release_at_0005_or_later_the_step_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = outcome(monkeypatch, head)
    assert kind == "skipped", reason
    assert f"head is {head}" in reason


@pytest.mark.parametrize("head", ["0003", "0001"])
def test_k06_a_previous_release_older_than_0004_fails_rather_than_skips(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    kind, reason = outcome(monkeypatch, head)
    assert kind == "failed", reason
    assert "must be published" in reason
