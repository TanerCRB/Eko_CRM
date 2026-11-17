"""EKO-1-34 (#192), transient: the probe's timing wrapper passes every outcome through unchanged."""

from pathlib import Path

import pytest

from tests.support import eko134_probe_timing as probe


class Fault(Exception):
    pass


def test_eko134_probe_wrapper_returns_the_helpers_result_and_marks_both_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "marks.log"
    monkeypatch.setenv(probe.TIMING_FILE, str(target))
    calls: list[tuple[object, ...]] = []

    def helper(*args: object, **kwargs: object) -> str:
        calls.append((*args, *kwargs.values()))
        return "result"

    assert probe.marked("helper", helper)(1, key=2) == "result"
    assert calls == [(1, 2)]
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 1)[1] for line in lines] == [
        "mark helper start",
        "mark helper returned",
    ]


def test_eko134_probe_wrapper_lets_the_same_exception_through_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "marks.log"
    monkeypatch.setenv(probe.TIMING_FILE, str(target))
    raised = Fault("navigation failed")
    calls: list[int] = []

    def helper() -> None:
        calls.append(1)
        raise raised

    with pytest.raises(Fault) as caught:
        probe.marked("helper", helper)()
    assert caught.value is raised
    assert calls == [1], "the helper ran more than once"
    assert target.read_text(encoding="utf-8").splitlines()[-1].endswith("mark helper raised")
    assert "navigation failed" not in target.read_text(encoding="utf-8")


def test_eko134_probe_writes_nothing_without_its_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(probe.TIMING_FILE, raising=False)
    monkeypatch.chdir(tmp_path)
    assert probe.marked("helper", lambda: 3)() == 3
    assert list(tmp_path.iterdir()) == []
