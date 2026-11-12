"""EKO-1-13 fix round 1 (Reviewer R-01, Security Auditor B-01): in the processes that serve
requests, a warning, an exception a finalizer raises and an exception in a thread are written in
the line form, never by Python's own printers (ADR-0005 addendum of 2026-11-02, as amended at
verification: the hook half is the first step of `create_app()`).

The served process is the composition's `backend` with its two uvicorn workers (fresh spawned
interpreters), running the shipped `serve.main` with the fixture's factory in a variant image that
only adds the fixture module. No test code installs a hook: whatever is in force is what the
served process installed itself. The whole container log is read.

Contrast: the same image with the one hook call removed from `create_app()` (a planted variant
that replaces `app/main.py`) puts the marker in the log, so the check can fail.
"""

from collections.abc import Iterator

import pytest

from tests.runtime.eko113 import (
    Window,
    backend_as,
    fixture_image,
    get_in_network,
    restore_backend,
    serve_command,
    wait_for_status,
)
from tests.runtime.lab import Lab
from tests.support import log_lines as ll
from tests.support.fixture_app import DRIVER_HOST, DRIVER_ROLE, DRIVER_URL, MARKER
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

BASE = "http://backend:8000"
ROUTES = ("/api/fixture/warn", "/api/fixture/unraisable", "/api/fixture/thread-error")
# Each route several times, so both workers are very likely to serve each at least once.
ROUNDS = 6
HOOK_CALL = "    install_interpreter_hooks()\n"
FORBIDDEN = (MARKER, DRIVER_HOST, DRIVER_ROLE, DRIVER_URL, "Traceback", "Exception ignored")


def served_log(lab: Lab, image: str) -> str:
    """The log of a `backend` running `image`'s `serve.main` after the fixture routes were hit."""
    served = backend_as(lab, image, serve_command("create"))
    try:
        served.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
        wait_for_status(lab, f"{BASE}/api/health", 200)
        for _ in range(ROUNDS):
            for route in ROUTES:
                assert get_in_network(lab, f"{BASE}{route}")["status"] == 200, route
        return Window(served.container_id("backend"), 0).text(settle=2)
    finally:
        restore_backend(lab)


@pytest.fixture(scope="module")
def shipped_log(lab: Lab) -> Iterator[str]:
    lab.at_head()
    yield served_log(lab, fixture_image(lab))


def test_adr0005_serving_process_hooks_only_line_form(shipped_log: str) -> None:
    lines, others = ll.json_lines(shipped_log)
    assert others == [], others[:5]
    assert [ll.app_line_problems(line) for line in lines] == [[] for _ in lines]
    assert ll.leaks(shipped_log, *FORBIDDEN) == []


def test_adr0005_serving_process_hooks_each_printer_wrote_its_line(shipped_log: str) -> None:
    """Not quiet by accident: each of the three reached the log, as a line of the form."""
    lines, _ = ll.json_lines(shipped_log)
    warned = [line for line in lines if line["logger"] == "py.warnings"]
    # S-5, option B: the category's type and the location, in the app.error key set, no text.
    assert warned, lines
    for line in warned:
        assert (line["event"], line["level"], line["error"]) == (
            "error", "WARNING", "builtins.UserWarning"), line  # fmt: skip
        assert line["at"].split(":")[1] == "add_fixture_routes.<locals>.warn", line
        assert "msg" not in line and "cause" not in line, line
    unhandled = [line for line in lines if line["logger"] == "app.unhandled"]
    assert {line["event"] for line in unhandled} == {"error"}, unhandled
    assert {line["error"] for line in unhandled} == {"builtins.RuntimeError"}, unhandled
    # The fixture module is outside app/, so `at` is its innermost frame: the raising function.
    functions = {line["at"].split(":")[1] for line in unhandled}
    finalizer = "RaisingFinalizer.__del__"
    in_thread = "add_fixture_routes.<locals>.thread_error.<locals>.fail"
    assert {finalizer, in_thread} <= functions, functions


def test_adr0005_serving_process_hooks_contrast_without_the_hook_install(lab: Lab) -> None:
    source = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert source.count(HOOK_CALL) == 1, "the planted contrast must remove exactly one call"
    planted = fixture_image(
        lab, {"/app/app/main.py": source.replace(HOOK_CALL, "")}, name="eko113_no_hooks"
    )
    lab.at_head()
    text = served_log(lab, planted)
    assert MARKER in text
    _, others = ll.json_lines(text)
    assert others, "Python's own printers wrote nothing outside the line form"
