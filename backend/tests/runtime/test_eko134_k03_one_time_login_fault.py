"""EKO-1-34 (#192) K-03: the fix masks nothing. A fault that happens once, on the first document
request of `browser_login`, still fails the login with that fault's error, and the login does not
send a second document request to the application to get past it.

The fault is a request interception that aborts the first document request to the application
origin with a connection reset and lets every other request through. A retry, a re-navigation or a
swallowed error around the first navigation would turn this into a completed login or a second
document request; the contrast is the same interception without the fault, which completes it.

On the session-wide `running` composition, with two invented accounts no other test uses there
(`eko201-login` and `eko201-logout` log in only on `keycloak_running`), so neither OTP enrolment
meets another. Synthetic data only.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Route, sync_playwright

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Composition, Started
from tests.runtime.eko134_host_network import settle_host_network

pytestmark = pytest.mark.runtime

FAULT = "connectionreset"
FAULT_ERROR = "net::ERR_CONNECTION_RESET"


class OneTimeFault:
    """Counts the document requests to the application origin; aborts the first one if armed."""

    def __init__(self, origin: str, armed: bool) -> None:
        self.origin = origin
        self.armed = armed
        self.documents: list[str] = []
        self.faults = 0

    def handle(self, route: Route) -> None:
        request = route.request
        if request.resource_type == "document" and request.url.startswith(self.origin + "/"):
            self.documents.append(request.url)
            if self.armed and self.faults == 0:
                self.faults += 1
                route.abort(FAULT)
                return
        route.continue_()


@contextmanager
def faulted_page(
    composition: Composition, chromium_executable: Path, fault: OneTimeFault
) -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[app.browser_host_rules(composition)],
        )
        try:
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.route("**/*", fault.handle)
            yield page
        finally:
            browser.close()


def test_eko134_k03_a_one_time_fault_on_the_first_login_navigation_fails_the_login(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    origin = app.app_origin(composition)
    username, password = app.provision_browser_account(composition, "logout")
    settle_host_network(composition)
    fault = OneTimeFault(origin, armed=True)
    with faulted_page(composition, chromium_executable, fault) as page:
        with pytest.raises(PlaywrightError) as raised:
            app.browser_login(page, composition, username, password)
    assert FAULT_ERROR in str(raised.value), str(raised.value)
    assert fault.faults == 1
    assert fault.documents == [origin + "/"], fault.documents


def test_eko134_k03_contrast_the_same_interception_without_the_fault_completes_the_login(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    origin = app.app_origin(composition)
    username, password = app.provision_browser_account(composition, "login")
    settle_host_network(composition)
    fault = OneTimeFault(origin, armed=False)
    with faulted_page(composition, chromium_executable, fault) as page:
        app.browser_login(page, composition, username, password)
        assert page.url == origin + "/", page.url
    assert fault.faults == 0
    assert fault.documents[0] == origin + "/"
    assert len(fault.documents) > 1, fault.documents
