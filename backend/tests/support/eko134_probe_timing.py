"""EKO-1-34 (#192), transient probe: wall-clock marks around the K-06 tests' set-up and login.

Loaded only by `.github/workflows/eko134-probe.yml` (`-p tests.support.eko134_probe_timing`) and
writing only when `EKO134_TIMING_FILE` names a file; no test imports it. It changes no harness
behavior: each wrapped helper gets the same arguments and its result or exception passes through
unchanged. A wrapper has no `except`; it writes one mark before the call and one in `finally`, so
nothing is caught, retried or re-navigated (K-03). Marks hold a helper name and an outcome only,
never an argument, a result or an error text. Removed together with the probe workflow (K-07).
"""

import functools
import os
import time
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

TIMING_FILE = "EKO134_TIMING_FILE"
# Helpers a K-06 test module calls by its own name (imported into the module).
MODULE_HELPERS = ("build_keycloak", "run_bootstrap")
# Helpers the K-06 tests call as attributes of `tests.runtime.eko201_login`.
LOGIN_MODULE = "tests.runtime.eko201_login"
LOGIN_HELPERS = ("provision_browser_account", "browser_login")
WRAPPED_FLAG = "__eko134_marked__"


def _target() -> Path | None:
    named = os.environ.get(TIMING_FILE, "")
    return Path(named) if named else None


def mark(text: str) -> None:
    """Append one timestamped line (UTC, microseconds) when the probe names a file."""
    target = _target()
    if target is None:
        return
    stamp = datetime.fromtimestamp(time.time(), UTC).isoformat(timespec="microseconds")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp.replace('+00:00', 'Z')} mark {text}\n")


def marked(name: str, helper: Callable[..., Any]) -> Callable[..., Any]:
    """The helper itself, with a mark before the call and one after it, whatever its outcome."""

    @functools.wraps(helper)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        mark(f"{name} start")
        outcome = "raised"
        try:
            result = helper(*args, **kwargs)
            outcome = "returned"
            return result
        finally:
            mark(f"{name} {outcome}")

    setattr(wrapper, WRAPPED_FLAG, True)
    return wrapper


def _wrap(module: ModuleType, names: tuple[str, ...]) -> None:
    for name in names:
        helper = getattr(module, name, None)
        if callable(helper) and not getattr(helper, WRAPPED_FLAG, False):
            setattr(module, name, marked(name, helper))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if _target() is None:
        return
    import importlib

    _wrap(importlib.import_module(LOGIN_MODULE), LOGIN_HELPERS)
    for item in items:
        module = getattr(item, "module", None)
        if isinstance(module, ModuleType):
            _wrap(module, MODULE_HELPERS)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, None, None]:
    mark(f"phase setup start {item.name}")
    try:
        return (yield)
    finally:
        mark(f"phase setup end {item.name}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, None, None]:
    mark(f"phase call start {item.name}")
    try:
        return (yield)
    finally:
        mark(f"phase call end {item.name}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, None, None]:
    mark(f"phase teardown start {item.name}")
    try:
        return (yield)
    finally:
        mark(f"phase teardown end {item.name}")
