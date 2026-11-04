"""EKO-1-13 fix round 1 (R-01, B-01), unit complement: `create_app()` installs the hook half of
the process logging as its first step (ADR-0005 addendum of 2026-11-02, as amended at
verification: *The single entries that install it*).

Uvicorn's worker processes are fresh interpreters that apply only `log_config`, so `create_app()`
is the one place a serving process gets the hooks. The proof on the served process is the runtime
file `test_adr0005_serving_process_hooks.py`; this pins the entry close to the code.

Each case checks inside the test body: pytest's thread-exception and unraisable-exception plugins
swap those hooks around each test phase.
"""

import logging
import sys
import threading
import warnings

import pytest

import app.core.logs as logs
from app.main import create_app
from tests.support.fixture_app import restored_process_state as restored


def hook_state() -> dict[str, object]:
    return {
        "excepthook": sys.excepthook,
        "threading.excepthook": threading.excepthook,
        "unraisablehook": sys.unraisablehook,
        "raiseExceptions": logging.raiseExceptions,
        "showwarning": warnings.showwarning,
    }


def some_other_printer(*args: object, **kwargs: object) -> None:
    """Stands in for whatever printer was in force before `create_app()`."""


EXPECTED = {
    "excepthook": logs._excepthook,
    "threading.excepthook": logs._thread_excepthook,
    "unraisablehook": logs._unraisablehook,
    "raiseExceptions": False,
    "showwarning": logs._showwarning,
}


def test_adr0005_create_app_installs_the_hook_half(backend_env: None) -> None:
    with restored():
        sys.excepthook = sys.__excepthook__
        threading.excepthook = threading.__excepthook__
        sys.unraisablehook = sys.__unraisablehook__
        logging.raiseExceptions = True
        warnings.showwarning = some_other_printer
        create_app()
        assert hook_state() == EXPECTED


def test_adr0005_create_app_installs_the_hooks_before_anything_can_fail(
    backend_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A settings failure is the first thing that can go wrong; the hooks are already in place."""
    monkeypatch.delenv("APP_DB_PASSWORD")
    with restored():
        sys.unraisablehook = sys.__unraisablehook__
        logging.raiseExceptions = True
        with pytest.raises(SystemExit):
            create_app()
        assert sys.unraisablehook is logs._unraisablehook
        assert logging.raiseExceptions is False
