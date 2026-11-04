"""EKO-1-13 fix round 1, stop S-5 (option B): a warning is written as its category's type and
code location only, in the `app.error` key set with `level` WARNING and `logger` py.warnings
(ADR-0005 addendum, amendment of 2026-11-04). No message text, source line or file path.

Contrast: the stdlib route the repository no longer uses (`logging.captureWarnings(True)`, one
element changed) writes the warning's text, marker included, so the leak check can fail.
"""

import logging
import warnings
from collections.abc import Callable, Iterator

import pytest

from tests.support import log_lines as ll
from tests.support.fixture_app import MARKER, install_for_test
from tests.support.fixture_app import restored_process_state as restored

Output = Callable[[], str]


@pytest.fixture
def output(capfd: pytest.CaptureFixture[str]) -> Iterator[Output]:
    with restored(), warnings.catch_warnings():
        install_for_test("backend")
        warnings.simplefilter("always")
        capfd.readouterr()

        def read() -> str:
            captured = capfd.readouterr()
            return captured.out + captured.err

        yield read


def warn_here() -> None:
    warnings.warn(f"serialized value may not be as expected [input_value={MARKER}]",
                  UserWarning, stacklevel=1)  # fmt: skip


def test_adr0005_warning_line_is_type_and_location(output: Output) -> None:
    warn_here()
    warnings.warn(f"deprecated {MARKER}", DeprecationWarning, stacklevel=1)
    text = output()
    lines, others = ll.json_lines(text)
    assert others == [], others
    assert [(line["event"], line["level"], line["logger"]) for line in lines] == [
        ("error", "WARNING", "py.warnings"),
        ("error", "WARNING", "py.warnings"),
    ]
    assert [line["error"] for line in lines] == [
        "builtins.UserWarning",
        "builtins.DeprecationWarning",
    ]
    assert lines[0]["at"].split(":")[:2] == [__name__, "warn_here"], lines[0]
    assert lines[1]["at"].split(":")[1] == "test_adr0005_warning_line_is_type_and_location"
    for line in lines:
        assert "cause" not in line and "msg" not in line
        assert ll.app_line_problems(line) == []
    assert ll.leaks(text, MARKER, "serialized value", ".py") == []


def test_adr0005_warning_line_carries_the_request_identifier(output: Output) -> None:
    from app.core.logs import correlation_id

    bound = correlation_id.set("ab" * 16)
    try:
        warn_here()
    finally:
        correlation_id.reset(bound)
    [line] = ll.json_lines(output())[0]
    assert line["correlation_id"] == "ab" * 16


def test_adr0005_warning_line_contrast_capture_warnings_leaks(output: Output) -> None:
    logging.captureWarnings(True)
    warn_here()
    assert MARKER in output()
