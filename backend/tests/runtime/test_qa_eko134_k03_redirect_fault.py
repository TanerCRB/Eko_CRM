"""QA, EKO-1-34 (#192) K-03: a one-time fault on the login's first redirect still fails the login.

K-03's own runtime test faults the first document request of `browser_login`, the `page.goto` of
the application origin. The CI failures this task fixes happened mostly one step later, in the
first `wait_for_url`: while the document navigation the application starts towards the auth host
(`/api/auth/login`, answered by a redirect to Keycloak) was in flight. A catch around that
`wait_for_url` that waits again, or that navigates again, is never reached by a fault at the
`goto`, so the goto fault alone does not show that nothing masks the failure site.

Here the interception aborts the first document request to the application's login endpoint,
once, and lets every other request through. (Playwright's route sees only the first URL of a
redirect chain, so the endpoint, not the auth host, is where a document fault can be placed.) The
login must fail with that fault's error, after exactly one document request to the application
root and one to the login endpoint. The contrast is the same interception unarmed, which
completes the login.

On the session-wide `running` composition, with two invented accounts no other test logs in
with there (`eko201-pages` and `eko201-mfa` are used only on `keycloak_running` and on the K-02
module's own composition). Each test has its own account, as K-03's own pair does: a mutation
that lets the armed login complete enrols that account's OTP, and must not turn the contrast red
with "no OTP enrolment demanded" (seen in QA's first mutation runs, when both shared one
account). Synthetic data only.
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
ARMED_ACCOUNT = "pages"
CONTRAST_ACCOUNT = "mfa"
LOGIN_ENDPOINT = "/api/auth/login"


class OneTimeRedirectFault:
    """Counts the document requests to the application origin; aborts the first one to the login
    endpoint if armed."""

    def __init__(self, origin: str, armed: bool) -> None:
        self.origin = origin
        self.armed = armed
        self.documents: list[str] = []
        self.faults = 0

    def handle(self, route: Route) -> None:
        request = route.request
        if request.resource_type == "document" and request.url.startswith(self.origin + "/"):
            self.documents.append(request.url)
            if (
                self.armed
                and self.faults == 0
                and request.url.startswith(self.origin + LOGIN_ENDPOINT)
            ):
                self.faults += 1
                route.abort(FAULT)
                return
        route.continue_()

    def endpoint_documents(self) -> list[str]:
        return [url for url in self.documents if url.startswith(self.origin + LOGIN_ENDPOINT)]


@contextmanager
def faulted_page(
    composition: Composition, chromium_executable: Path, fault: OneTimeRedirectFault
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


def test_qa_eko134_k03_a_one_time_fault_on_the_first_redirect_fails_the_login(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    origin = app.app_origin(composition)
    username, password = app.provision_browser_account(composition, ARMED_ACCOUNT)
    settle_host_network(composition)
    fault = OneTimeRedirectFault(origin, armed=True)
    with faulted_page(composition, chromium_executable, fault) as page:
        with pytest.raises(PlaywrightError) as raised:
            app.browser_login(page, composition, username, password)
    assert FAULT_ERROR in str(raised.value), str(raised.value)
    assert fault.faults == 1
    assert fault.documents[0] == origin + "/", fault.documents
    assert len(fault.documents) == 2, fault.documents
    assert len(fault.endpoint_documents()) == 1, fault.documents


def test_qa_eko134_k03_contrast_the_same_redirect_interception_unarmed_completes_the_login(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    origin = app.app_origin(composition)
    username, password = app.provision_browser_account(composition, CONTRAST_ACCOUNT)
    settle_host_network(composition)
    fault = OneTimeRedirectFault(origin, armed=False)
    with faulted_page(composition, chromium_executable, fault) as page:
        app.browser_login(page, composition, username, password)
        assert page.url == origin + "/", page.url
    assert fault.faults == 0
    assert fault.documents[0] == origin + "/", fault.documents
    assert len(fault.endpoint_documents()) == 1, fault.documents
