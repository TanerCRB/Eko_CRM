"""EKO-2-02 K-08, composed browser leg: a staff account whose client roles were stripped logs in
through the public listener, the real backend and running Keycloak with MFA, and the SPA offers it
a working logout.

- After the login the SPA shows the no-role screen: a logout action, no shell (main navigation,
  account region) and no second login start.
- Clicking logout ends the application session (the row is gone, the old cookie gets 401 and is
  cleared in the browser) and the Keycloak SSO session: the next visit lands on Keycloak's login
  form, not a silent re-login.

Contrast: the same account with `rep` reaches the shell, and its logout lives in the account
panel; that is EKO-2-01's `test_eko201_k03_shell_browser.py`. The roles are stripped by the
break-glass administrator; `identity/` is not touched. When EKO201_SCREENSHOT_DIR is set,
screenshots are written there (outside the repository).
"""

import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Request, expect, sync_playwright

from tests.runtime import eko201_login as login_flow
from tests.runtime import eko202_live as live
from tests.runtime.conftest import Composition, Started

pytestmark = pytest.mark.runtime

NAVIGATION = "Nawigacja główna"
ACCOUNT = "Konto"
LOGOUT = "Wyloguj się"
TIMEOUT_MS = 30_000


def login_starts(page: Page, composition: Composition) -> list[str]:
    """The `return_to` of every login start the page's main frame navigates to, in order."""
    origin = login_flow.app_origin(composition)
    found: list[str] = []

    def seen(request: Request) -> None:
        parts = urlsplit(request.url)
        if (
            request.is_navigation_request()
            and request.frame == page.main_frame
            and f"{parts.scheme}://{parts.netloc}" == origin
            and parts.path == "/api/auth/login"
        ):
            found.extend(parse_qs(parts.query, keep_blank_values=True).get("return_to", [""]))

    page.on("request", seen)
    return found


def shot(page: Page, name: str) -> None:
    target = os.environ.get("EKO201_SCREENSHOT_DIR")
    if target:
        directory = Path(target) / "eko202-k08"
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / f"{name}.png"), full_page=True)


def test_k08_role_less_account_logs_out_from_the_no_role_screen(
    keycloak_running: Started, chromium_executable: Path
) -> None:
    composition = keycloak_running.composition
    realm = live.Realm(composition)
    username, password = live.unique("k08"), live.new_password()
    user_id = realm.create_account(username, password, ["rep"])
    realm.change_roles(user_id, "DELETE", ["rep"])
    assert realm.role_names(user_id) == set(), "premise: the account holds no client role"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[login_flow.browser_host_rules(composition)],
        )
        try:
            context = browser.new_context(
                ignore_https_errors=True, viewport={"width": 1280, "height": 900}, locale="pl-PL"
            )
            page = context.new_page()
            starts = login_starts(page, composition)
            before = login_flow.session_count(composition)
            login_flow.browser_login(page, composition, username, password, "/")
            assert login_flow.session_count(composition) == before + 1
            cookie = next(c for c in context.cookies() if c["name"] == login_flow.SESSION_COOKIE)
            session = str(cookie["value"])
            # The backend's answer the SPA meets: authenticated, no role.
            assert login_flow.session_view(composition, session).status_code == 403

            # The no-role screen: a logout action, no shell, no second login start.
            logout = page.get_by_role("button", name=LOGOUT)
            expect(logout).to_be_visible(timeout=TIMEOUT_MS)
            expect(page.get_by_role("navigation", name=NAVIGATION)).to_have_count(0)
            expect(page.get_by_role("region", name=ACCOUNT)).to_have_count(0)
            page.wait_for_load_state("networkidle")
            assert starts == ["/"], f"login starts after landing: {starts}"
            shot(page, "no-role-screen")

            logout.click()
            auth_host = composition.env["AUTH_HOST"]
            page.wait_for_url(lambda url: urlsplit(url).hostname == auth_host, timeout=TIMEOUT_MS)
            page.wait_for_load_state("networkidle")
            assert page.locator("#kc-form-login").count() == 1, "silent re-login after logout"
            assert starts[-1] == "/", f"logout did not load the root: {starts}"
            assert login_flow.session_count(composition) == before
            assert login_flow.session_view(composition, session).status_code == 401
            assert not [c for c in context.cookies() if c["name"] == login_flow.SESSION_COOKIE]
            shot(page, "after-logout")
            context.close()
        finally:
            browser.close()
