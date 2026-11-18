"""EKO-1-34 probe r1, transient, probe-only: one log line per settle_host_network call.

Loaded with `-p eko134_probe_settle_log` by `.github/workflows/eko134-probe-r1.yml` only, on the
throwaway branch EKO-1-34-probe-r1, never part of the PR. Logging only. It wraps the settle
module's attribute (the K-02 module calls `host.settle_host_network`) and the name a test module
imported (the K-06 tests). The settle's arguments, result and exception pass through unchanged,
and nothing is caught: the outcome is read from `sys.exc_info()` in `finally`. The line names the
exception and its message, so the continuous-interference test's elapsed time and message reach
the log even when that test passes.
"""

import functools
import importlib
import logging
import sys
import time
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

HOST_MODULE = "tests.runtime.eko134_host_network"
NAME = "settle_host_network"
FLAG = "__eko134_probe_r1_logged__"
logger = logging.getLogger("eko134.probe")


def logged(helper: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(helper)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        result = None
        try:
            result = helper(*args, **kwargs)
            return result
        finally:
            elapsed = time.monotonic() - started
            raised = sys.exc_info()[1]
            if raised is not None:
                logger.info(
                    "eko134-probe settle raised %s after %.3f s: %s",
                    type(raised).__name__,
                    elapsed,
                    str(raised).replace("\n", " "),
                )
            else:
                logger.info(
                    "eko134-probe settle returned applies=%s waited=%.2f interfaces=%d after %.3f s",
                    getattr(result, "applies", None),
                    getattr(result, "waited_seconds", 0.0),
                    len(getattr(result, "interfaces", ())),
                    elapsed,
                )

    setattr(wrapper, FLAG, True)
    return wrapper


def wrap(module: ModuleType) -> None:
    helper = getattr(module, NAME, None)
    if callable(helper) and not getattr(helper, FLAG, False):
        setattr(module, NAME, logged(helper))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    wrap(importlib.import_module(HOST_MODULE))
    for item in items:
        module = getattr(item, "module", None)
        if isinstance(module, ModuleType):
            wrap(module)
