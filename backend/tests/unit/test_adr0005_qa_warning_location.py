"""EKO-1-13 re-verification (QA): the `at` rule of a warning line, and the C2 notice.

ADR-0005 addendum, amendment of 2026-11-04 (S-5, option B): a warning line's `at` follows the
rule of an exception, the innermost frame of the application's own code on the stack down to the
frame the warning names, else that frame. The developer's tests warn from test code only, with
no application frame on the stack, so a rule that always names the warning's own frame passes
them. These cases put one application frame on the stack. The frame is code compiled under a
file name in `app/` (no file is written there), so `_module_of` reads it as the application's.

The C2 notice (K-04: the real-app C2 check never passes silently on an empty set) must still
reach pytest's warning record now that `create_app()` installs the repository's printer.
"""

import warnings
from collections.abc import Callable, Iterator

import pytest

import app.core.logs as logs
import tests.unit.test_adr0005_c2_validation_input_not_logged as c2
from app.main import create_app
from tests.support import log_lines as ll
from tests.support.fixture_app import MARKER, install_for_test
from tests.support.fixture_app import restored_process_state as restored

Output = Callable[[], str]
PROBE_MODULE = "app.qa_warning_probe"
PROBE_FILE = str(logs.BACKEND_ROOT / "app" / "qa_warning_probe.py")
PROBE_SOURCE = "def probe(callback):\n    callback()\n"
PROBE_LINE = 2
EXPLICIT_FILE = "/nowhere/qa_library/explicit.py"


def application_probe() -> Callable[[Callable[[], None]], None]:
    namespace: dict[str, object] = {"__name__": PROBE_MODULE}
    exec(compile(PROBE_SOURCE, PROBE_FILE, "exec"), namespace)  # noqa: S102
    probe = namespace["probe"]
    assert callable(probe)
    return probe


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


def library_warns() -> None:
    warnings.warn(f"library value {MARKER}", UserWarning, stacklevel=1)


def only_warning_line(text: str) -> dict[str, str]:
    lines, others = ll.json_lines(text)
    assert others == [], others
    assert len(lines) == 1, lines
    [line] = lines
    assert (line["event"], line["level"], line["logger"]) == ("error", "WARNING", "py.warnings")
    assert ll.leaks(text, MARKER, "library value", ".py") == []
    return line


def test_adr0005_qa_warning_at_names_the_application_frame(output: Output) -> None:
    application_probe()(library_warns)
    line = only_warning_line(output())
    assert line["at"] == f"{PROBE_MODULE}:probe:{PROBE_LINE}", line


def test_adr0005_qa_warning_at_contrast_without_an_application_frame(output: Output) -> None:
    """One element changed: the same warning, with no application frame on the stack."""
    library_warns()
    line = only_warning_line(output())
    assert line["at"].split(":")[:2] == [__name__, "library_warns"], line


def test_adr0005_qa_warning_at_explicit_location_skips_the_printer(output: Output) -> None:
    """A warning given a location no frame matches: `at` is the stack outside the warning
    machinery, never the repository's printer, and the given file path is not written."""
    warnings.warn_explicit(f"library value {MARKER}", UserWarning, EXPLICIT_FILE, 7)
    text = output()
    line = only_warning_line(text)
    assert line["at"].split(":")[:2] == [
        __name__,
        "test_adr0005_qa_warning_at_explicit_location_skips_the_printer",
    ], line
    assert ll.leaks(text, EXPLICIT_FILE, "qa_library") == []


def c2_notice_run(capfd: pytest.CaptureFixture[str]) -> None:
    """The real-app C2 test as pytest runs it, with its own fixture's set-up."""
    with restored():
        install_for_test("backend")
        capfd.readouterr()
        c2.test_adr0005_c2_validation_input_not_logged_on_every_body_route(
            None, lambda: capfd.readouterr().err
        )


def test_adr0005_qa_c2_notice_reaches_pytest_record(
    backend_env: None, capfd: pytest.CaptureFixture[str]
) -> None:
    with pytest.warns(UserWarning, match=r"ADR-0005-C2: create_app\(\) declares \d+ route"):
        c2_notice_run(capfd)


def test_adr0005_qa_c2_notice_contrast_installed_printer_hides_it(
    backend_env: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """One element changed: the same notice through the printer `create_app()` installs is not
    recorded, so the check above can fail."""
    with restored(), warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        create_app()
        warnings.warn("ADR-0005-C2: create_app() declares 0 route(s)", UserWarning, stacklevel=1)
    assert recorded == []
