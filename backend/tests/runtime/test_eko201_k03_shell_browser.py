"""EKO-2-01 K-03, composed: a real browser through the public listener, the real backend and
running Keycloak with MFA, against the SPA's session gate.

- Anonymous deep links (`/`, `/klienci`, `/klienci?x=1`) are sent to `/api/auth/login` with the
  exact `return_to`, and no shell (main navigation, account region) renders.
- An invented company account with no linked Google or other identity provider logs in on
  Keycloak's pages, enrols its OTP credential, and lands on the destination it asked for, with
  the shell and its own display name in the account region; a reload keeps it in the shell.
- The browser presents `__Host-eko_session` on its own `/api/auth/session` call: the
  `SameSite=Strict` session cookie reaches the backend after a login that ended with a
  cross-site redirect chain from `<auth-host>`.
- Logout ends in a full load of `/` that is sent to login with `return_to=%2F`; the old cookie
  then gets 401 on `/api/auth/session`, and Keycloak shows its form again (no silent SSO).

Contrasts inside the test: the same deep links, with a valid session, render the shell with no
login redirect; invalid company credentials end on Keycloak's error page, create no
application session and render no shell. When EKO201_SCREENSHOT_DIR is set, screenshots of
each state are written there (outside the repository).
"""

import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Request, expect, sync_playwright

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Composition, Started
from tests.runtime.keycloak_client import RealmClient
from tests.support import eko112_fixtures as eko112
from tests.support import eko201_keycloak as accounts
from tests.support import totp

pytestmark = pytest.mark.runtime
NAVIGATION = "Nawigacja główna"
ACCOUNT = "Konto"
LOGOUT = "Wyloguj się"
DEEP_LINKS = [("/", "Pulpit"), ("/klienci", "Klienci"), ("/klienci?x=1", "Klienci")]
TIMEOUT_MS = 30_000


def login_target(url: str, composition: Composition) -> str | None:
    """The `return_to` of a login start, if `url` is one on the application's origin."""
    parts = urlsplit(url)
    if f"{parts.scheme}://{parts.netloc}" != app.app_origin(composition):
        return None
    if parts.path != "/api/auth/login":
        return None
    values = parse_qs(parts.query, keep_blank_values=True).get("return_to", [])
    return values[0] if len(values) == 1 else None


def started_logins(page: Page, composition: Composition) -> list[str]:
    """Every login start the page's main frame navigated to, in order."""
    found: list[str] = []

    def seen(request: Request) -> None:
        if request.is_navigation_request() and request.frame == page.main_frame:
            target = login_target(request.url, composition)
            if target is not None:
                found.append(target)

    page.on("request", seen)
    return found


def at_keycloak_form(page: Page, composition: Composition) -> bool:
    """Wait until the page is on `<auth-host>` and say whether it shows Keycloak's login form."""
    auth_host = composition.env["AUTH_HOST"]
    page.wait_for_url(lambda url: urlsplit(url).hostname == auth_host, timeout=TIMEOUT_MS)
    page.wait_for_load_state("networkidle")
    return page.locator("#kc-form-login").count() == 1


def shell_absent(page: Page) -> None:
    expect(page.get_by_role("navigation", name=NAVIGATION)).to_have_count(0)
    expect(page.get_by_role("region", name=ACCOUNT)).to_have_count(0)


def shell_present(page: Page, heading: str) -> None:
    expect(page.get_by_role("navigation", name=NAVIGATION)).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.get_by_role("heading", level=1, name=heading)).to_be_visible()
    account = page.get_by_role("region", name=ACCOUNT)
    expect(account).to_contain_text(accounts.DISPLAY_NAME)
    expect(account.get_by_role("button", name=LOGOUT)).to_be_visible()


class Shots:
    def __init__(self) -> None:
        target = os.environ.get("EKO201_SCREENSHOT_DIR")
        self.target = Path(target) / "k03" if target else None
        if self.target is not None:
            self.target.mkdir(parents=True, exist_ok=True)

    def take(self, page: Page, name: str) -> None:
        if self.target is not None:
            page.screenshot(path=str(self.target / f"{name}.png"), full_page=True)


def type_credentials(page: Page, username: str, password: str) -> None:
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#kc-login")
    page.wait_for_load_state("networkidle")


def enrol(page: Page, username: str) -> None:
    """Answer Keycloak's enrolment page with a code for the secret it shows (never logged)."""
    raw = page.locator("#totpSecret").input_value()
    page.fill("#totp", totp.totp(totp.keycloak_key(raw), totp.time_step()))
    page.fill("#userLabel", f"{username}-browser-{secrets.token_hex(3)}")
    page.locator("#saveTOTPBtn").click()


def new_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        ignore_https_errors=True, viewport={"width": 1280, "height": 900}, locale="pl-PL"
    )


def run_k03(started: Started, chromium_executable: Path) -> None:
    """The scenario, callable on any bootstrapped composition (the fail-first run calls it on a
    composition serving the frontend from before the session gate)."""
    composition = started.composition
    env = composition.env
    origin = app.app_origin(composition)
    master = RealmClient(composition, "master")
    shots = Shots()
    try:
        token = master.direct_master_token(
            eko112.ACCOUNTS["breakglass_one"], env[eko112.PASSWORD_VARIABLES["breakglass_one"]]
        )
        password = "synthetic-" + secrets.token_urlsafe(24)
        username = accounts.ACCOUNTS["shell"]
        user_id = app.ensure_staff_account(master, token, "shell", password)
        assert master.admin_json(token, "GET", "identity-provider/instances", realm="eko") == []
        assert (
            master.admin_json(token, "GET", f"users/{user_id}/federated-identity", realm="eko")
            == []
        )
    finally:
        master.close()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[
                f"--host-resolver-rules=MAP {env['APP_HOST']} 127.0.0.1, "
                f"MAP {env['AUTH_HOST']} 127.0.0.1"
            ],
        )
        try:
            # 1. Anonymous deep links: login start with the exact return_to, no shell.
            for path, _heading in DEEP_LINKS:
                context = new_context(browser)
                page = context.new_page()
                logins = started_logins(page, composition)
                page.goto(origin + path)
                assert at_keycloak_form(page, composition), f"{path}: not at Keycloak's form"
                assert logins == [path], f"{path}: login starts {logins}"
                shell_absent(page)
                shots.take(page, f"anonymous-{path.strip('/').replace('?', '-') or 'root'}")
                context.close()

            # 2. Invalid company credentials: Keycloak's error page, no session, no shell.
            sessions_before = app.session_count(composition)
            context = new_context(browser)
            page = context.new_page()
            page.goto(origin + "/klienci")
            type_credentials(page, username, password + "-wrong")
            assert at_keycloak_form(page, composition), "invalid credentials left the login form"
            shell_absent(page)
            assert app.session_count(composition) == sessions_before
            assert not [c for c in context.cookies() if c["name"] == app.SESSION_COOKIE]
            shots.take(page, "invalid-credentials")
            context.close()

            # 3. Login without Google, with OTP enrolment, to the requested deep link.
            context = new_context(browser)
            page = context.new_page()
            presented: list[str] = []

            def session_call(request: Request) -> None:
                if urlsplit(request.url).path == "/api/auth/session":
                    cookie = request.all_headers().get("cookie", "")
                    presented.append(cookie)

            page.on("request", session_call)
            logins = started_logins(page, composition)
            page.goto(origin + "/klienci?x=1")
            assert at_keycloak_form(page, composition)
            type_credentials(page, username, password)
            assert page.locator("#totpSecret").count() == 1, "no OTP enrolment demanded"
            shots.take(page, "enrolment")
            enrol(page, username)
            page.wait_for_url(origin + "/klienci?x=1", timeout=TIMEOUT_MS)
            shell_present(page, "Klienci")
            assert logins == ["/klienci?x=1"]
            assert app.session_count(composition) == sessions_before + 1
            # The browser itself presented the session cookie on the gate's session call.
            assert any(f"{app.SESSION_COOKIE}=" in cookie for cookie in presented), (
                "the browser did not present the session cookie"
            )
            cookie = next(c for c in context.cookies() if c["name"] == app.SESSION_COOKIE)
            assert cookie["httpOnly"] and cookie["secure"] and cookie["sameSite"] == "Strict"
            assert "domain" not in cookie or not str(cookie["domain"]).startswith(".")
            shots.take(page, "shell-after-login")

            # 4. Reload, and every deep link with the valid session: shell, no login start.
            page.reload()
            shell_present(page, "Klienci")
            for path, heading in DEEP_LINKS:
                page.goto(origin + path)
                shell_present(page, heading)
            assert logins == ["/klienci?x=1"], f"a valid session was sent to login: {logins}"
            old_session = cookie["value"]
            assert app.session_view(composition, old_session).status_code == 200

            # 5. Logout: full load of `/`, sent to login with return_to=%2F, form shown again.
            page.goto(origin + "/klienci")
            shell_present(page, "Klienci")
            page.get_by_role("region", name=ACCOUNT).get_by_role("button", name=LOGOUT).click()
            assert at_keycloak_form(page, composition), "after logout: no login form (silent SSO?)"
            assert logins[-1] == "/", f"after logout: login starts {logins}"
            shell_absent(page)
            assert app.session_view(composition, old_session).status_code == 401
            assert not [c for c in context.cookies() if c["name"] == app.SESSION_COOKIE]
            shots.take(page, "after-logout")
            context.close()
        finally:
            browser.close()


def test_k03_anonymous_deep_links_login_without_google_reload_and_logout(
    keycloak_running: Started, chromium_executable: Path
) -> None:
    run_k03(keycloak_running, chromium_executable)
