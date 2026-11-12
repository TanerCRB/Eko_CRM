"""EKO-1-13 K-05 and K-04, QA addition: the interpreter's own error printers write the line form,
not a traceback (ADR-0005 addendum of 2026-11-02, *An error outside a request*;
`install_process_logging` in `app.core.logs`).

K-05's boundary is the process's whole output, which Python's default exception hook writes to
past the application's logging. `install_process_logging` replaces three printers (the exception
hook, the thread exception hook and the unraisable hook) and turns off `logging.raiseExceptions`,
whose handler-error print carries the record's message and arguments. No test exercised any of the
four: removing them (mutations EKO-1-13/M23 and M24) left the whole suite green.

Each case installs the process logging inside the test body: pytest's own thread-exception and
unraisable-exception plugins swap those hooks around each test phase, so a hook installed by a
fixture would not be the one in force. Each case has a contrast in which the one element changed is
the printer the repository replaces, and the marker then reaches the output.
"""

import gc
import io
import logging
import sys
import threading
from collections.abc import Callable, Iterator

import pytest

from tests.support import log_lines as ll
from tests.support.fixture_app import MARKER, install_for_test
from tests.support.fixture_app import restored_process_state as restored

Output = Callable[[], str]


@pytest.fixture
def output(capfd: pytest.CaptureFixture[str]) -> Iterator[Output]:
    """Both captures: the line form writes to fd 2; Python's printers write to `sys.stderr`."""
    with restored():
        capfd.readouterr()

        def read() -> str:
            captured = capfd.readouterr()
            return captured.out + captured.err

        yield read


def raised() -> RuntimeError:
    try:
        try:
            raise ValueError(f"inner {MARKER}")
        except ValueError as inner:
            raise RuntimeError(f"outer {MARKER}") from inner
    except RuntimeError as exc:
        return exc


def one_error_line(text: str, logger: str) -> list[str]:
    lines, others = ll.json_lines(text)
    problems = [f"not the line form: {line[:200]!r}" for line in others]
    errors = [line for line in lines if line.get("event") == "error"]
    if len(errors) != 1:
        problems.append(f"{len(errors)} error lines: {lines}")
    for line in errors:
        if (line.get("logger"), line.get("error")) != (logger, "builtins.RuntimeError"):
            problems.append(f"error line {line}")
        problems += ll.app_line_problems(line)
    problems += [f"leaked {needle!r}" for needle in ll.leaks(text, MARKER, "Traceback")]
    return problems


def test_adr0005_qa_excepthook_writes_the_line_form(output: Output) -> None:
    install_for_test("worker")
    exc = raised()
    sys.excepthook(type(exc), exc, exc.__traceback__)
    assert one_error_line(output(), "app.unhandled") == []


def test_adr0005_qa_excepthook_contrast_default_hook_prints_the_marker(output: Output) -> None:
    install_for_test("worker")
    exc = raised()
    sys.__excepthook__(type(exc), exc, exc.__traceback__)
    text = output()
    assert "Traceback" in text and ll.leaks(text, MARKER) == [MARKER]


def run_failing_thread() -> None:
    def fail() -> None:
        raise raised()

    thread = threading.Thread(target=fail, name="eko113-qa")
    thread.start()
    thread.join()


def test_adr0005_qa_thread_excepthook_writes_the_line_form(output: Output) -> None:
    install_for_test("worker")
    run_failing_thread()
    assert one_error_line(output(), "app.unhandled") == []


def test_adr0005_qa_thread_excepthook_contrast_default_hook_prints_the_marker(
    output: Output,
) -> None:
    install_for_test("worker")
    threading.excepthook = threading.__excepthook__
    run_failing_thread()
    text = output()
    assert "Traceback" in text and ll.leaks(text, MARKER) == [MARKER]


class RaisesWhenCollected:
    def __del__(self) -> None:
        raise raised()


def drop_one() -> None:
    RaisesWhenCollected()
    gc.collect()


def test_adr0005_qa_unraisablehook_writes_the_line_form(output: Output) -> None:
    install_for_test("worker")
    drop_one()
    assert one_error_line(output(), "app.unhandled") == []


def test_adr0005_qa_unraisablehook_contrast_default_hook_prints_the_marker(
    output: Output,
) -> None:
    install_for_test("worker")
    sys.unraisablehook = sys.__unraisablehook__
    drop_one()
    text = output()
    assert "Traceback" in text and ll.leaks(text, MARKER) == [MARKER]


class BrokenStream(io.TextIOBase):
    def write(self, text: str) -> int:
        raise OSError("the log stream is gone")


def log_to_a_broken_stream() -> None:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(BrokenStream())
    logging.getLogger("app.fixture").error("a value %s", MARKER)


def test_adr0005_qa_failing_handler_prints_nothing(output: Output) -> None:
    install_for_test("worker")
    log_to_a_broken_stream()
    text = output()
    assert ll.leaks(text, MARKER, "Logging error", "Traceback") == [], text


def test_adr0005_qa_failing_handler_contrast_raise_exceptions_prints_the_arguments(
    output: Output,
) -> None:
    install_for_test("worker")
    logging.raiseExceptions = True
    log_to_a_broken_stream()
    text = output()
    assert "Logging error" in text and ll.leaks(text, MARKER) == [MARKER]
