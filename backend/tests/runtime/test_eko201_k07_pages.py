"""EKO-2-01 K-07 against the running composition: theme selection and the page policy.

ADR-0003-C30 (live half): the login page served through the public listener comes from the
`eko-crm` theme, declares Polish and offers no language selector; the master realm sets no
theme. Contrast: with only `loginTheme` removed from the application realm, the same request
returns the parent theme's page and the selection check fails.

Page policy (automated half): a real browser walks the login, invalid-credentials (with a
typed username holding markup, shown escaped), lockout, password-reset, MFA enrolment,
required password, MFA code and refused-code pages; each page must show Polish wording and the
Eko_CRM name and no default-English replacement. One-change contrasts on a captured page (its
language, the name, one Polish phrase) fail the check. When EKO201_EVIDENCE_DIR is set, the
redacted HTML is written there; when EKO201_SCREENSHOT_DIR is set, screenshots (desktop and a
narrow mobile viewport, the enrolment QR code masked) are written there. Screenshots are binary
and stay outside the repository (the change-set scans read every added file as text). Both
serve the human review of linguistic adequacy and visual acceptability, which no test decides.
"""

import json
import os
import re
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, sync_playwright

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Composition, Started
from tests.runtime.keycloak_client import RealmClient, callback_uri
from tests.support import eko112_fixtures as eko112
from tests.support import eko201_keycloak as accounts
from tests.support import totp
from tests.support.theme_checks import THEME_NAME

pytestmark = pytest.mark.runtime
THEME_KEYS = ("loginTheme", "accountTheme", "adminTheme", "emailTheme")


@pytest.fixture
def master(keycloak_running: Started) -> Iterator[RealmClient]:
    client = RealmClient(keycloak_running.composition, "master")
    try:
        yield client
    finally:
        client.close()


def breakglass(master: RealmClient) -> str:
    env = master.composition.env
    return master.direct_master_token(
        eko112.ACCOUNTS["breakglass_one"], env[eko112.PASSWORD_VARIABLES["breakglass_one"]]
    )


def login_page(composition: Composition) -> str:
    client = RealmClient(composition, "eko", listener="auth")
    try:
        query = (
            f"client_id=eko-backend&redirect_uri={callback_uri(composition)}"
            "&response_type=code&scope=openid&code_challenge="
            + "A" * 43
            + "&code_challenge_method=S256&state=eko201-selection"
        )
        page = client.request("GET", f"/realms/eko/protocol/openid-connect/auth?{query}")
        assert page.status_code == 200, page.status_code
        return page.text
    finally:
        client.close()


def selection_findings(document: str) -> list[str]:
    problems = []
    if f"/login/{THEME_NAME}/" not in document:
        problems.append("the page does not come from the selected theme")
    if not re.search(r'<html\b[^>]*\blang="pl"', document):
        problems.append("the page does not declare Polish")
    if "login-select-toggle" in document:
        problems.append("a language selector is offered")
    return problems


def test_k07_c30_live_page_comes_from_the_theme_and_only_login_theme_selects_it(
    keycloak_running: Started, master: RealmClient
) -> None:
    composition = keycloak_running.composition
    token = breakglass(master)
    master_realm = master.admin_json(token, "GET", "", realm="master")
    assert [key for key in THEME_KEYS if master_realm.get(key)] == [], (
        "the master realm sets a theme"
    )
    realm = master.admin_json(token, "GET", "", realm="eko")
    assert realm["loginTheme"] == THEME_NAME
    assert [key for key in THEME_KEYS[1:] if realm.get(key)] == []
    assert selection_findings(login_page(composition)) == []
    try:
        realm["loginTheme"] = ""
        assert master.admin(token, "PUT", "", json_body=realm, realm="eko").status_code == 204
        parent = login_page(composition)
        assert "/login/keycloak.v2/" in parent, "the parent theme's page was not served"
        assert "the page does not come from the selected theme" in selection_findings(parent)
    finally:
        realm["loginTheme"] = THEME_NAME
        assert master.admin(token, "PUT", "", json_body=realm, realm="eko").status_code == 204
    assert selection_findings(login_page(composition)) == []


# Page policy ---------------------------------------------------------------------------------


class Capture:
    """Checks each page and, when asked, writes it (redacted) and its screenshots."""

    def __init__(self, target: Path | None, screenshots: Path | None) -> None:
        self.target = target
        self.screenshots = screenshots
        self.secrets: list[str] = []
        self.pages: dict[str, str] = {}
        for directory in (target, screenshots):
            if directory is not None:
                directory.mkdir(parents=True, exist_ok=True)

    def take(self, state: str, page: Page, masked: list[Locator] | None = None) -> None:
        document = page.content()
        assert accounts.page_findings(state, document) == []
        self.pages[state] = document
        if self.target is not None:
            self.write_html(state, document)
        if self.screenshots is not None:
            self.shoot(state, page, masked or [])

    def write_html(self, state: str, document: str) -> None:
        assert self.target is not None
        redacted = accounts.redact_page(document, self.secrets)
        for secret in self.secrets:
            for form in accounts.secret_forms(secret).values():
                assert form.casefold() not in redacted.casefold(), "redaction left a secret"
        # The enrolment QR code encodes the secret: no embedded image data may remain.
        assert not re.search(r"base64,\s*[A-Za-z0-9+/]{32}", redacted), "embedded image data"
        (self.target / f"{state}.html").write_text(redacted, encoding="utf-8")

    def shoot(self, state: str, page: Page, mask: list[Locator]) -> None:
        assert self.screenshots is not None
        page.screenshot(path=str(self.screenshots / f"{state}.png"), full_page=True, mask=mask)
        size = page.viewport_size
        page.set_viewport_size({"width": 360, "height": 780})
        narrow = self.screenshots / f"{state}-narrow.png"
        page.screenshot(path=str(narrow), full_page=True, mask=mask)
        if size is not None:
            page.set_viewport_size(size)


def test_k07_page_policy_on_every_page_state(
    keycloak_running: Started, master: RealmClient, chromium_executable: Path
) -> None:
    composition = keycloak_running.composition
    env = composition.env
    token = breakglass(master)
    pages_password = "synthetic-" + secrets.token_urlsafe(24)
    locked_password = "synthetic-" + secrets.token_urlsafe(24)
    temporary = "synthetic-" + secrets.token_urlsafe(24)
    updated = "synthetic-" + secrets.token_urlsafe(24)
    app.ensure_staff_account(master, token, "pages", pages_password)
    app.ensure_staff_account(master, token, "locked", locked_password)
    app.ensure_staff_account(master, token, "required", temporary, temporary=True)
    evidence = os.environ.get("EKO201_EVIDENCE_DIR")
    shots = os.environ.get("EKO201_SCREENSHOT_DIR")
    capture = Capture(Path(evidence) if evidence else None, Path(shots) if shots else None)
    login_url = f"{app.app_origin(composition)}/api/auth/login?return_to=%2F"

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

            def fresh_page() -> Page:
                context = browser.new_context(
                    ignore_https_errors=True,
                    viewport={"width": 1280, "height": 900},
                    locale="pl-PL",
                )
                return context.new_page()

            page = fresh_page()
            page.goto(login_url, wait_until="networkidle")
            capture.take("login", page)
            page.fill("#username", accounts.MARKUP_USERNAME)
            page.fill("#password", "synthetic-wrong-" + secrets.token_hex(6))
            page.click("#kc-login")
            page.wait_for_load_state("networkidle")
            capture.take("login-error", page)
            document = capture.pages["login-error"]
            assert accounts.MARKUP_USERNAME not in document, "the typed markup is not escaped"
            assert "&lt;b&gt;marker&lt;/b&gt;" in document

            for attempt in range(5):
                page.fill("#username", accounts.ACCOUNTS["locked"])
                page.fill("#password", f"synthetic-wrong-{attempt}-{secrets.token_hex(4)}")
                page.click("#kc-login")
                page.wait_for_load_state("networkidle")
            page.fill("#username", accounts.ACCOUNTS["locked"])
            page.fill("#password", locked_password)
            page.click("#kc-login")
            page.wait_for_load_state("networkidle")
            assert page.locator("#password").count() == 1, "the locked account got in"
            capture.take("lockout", page)

            page.click("text=Nie pamiętasz hasła?")
            page.wait_for_load_state("networkidle")
            capture.take("reset", page)
            page.fill("#username", accounts.ADDRESSES["pages"])
            page.locator("input[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("networkidle")
            capture.take("reset-sent", page)

            page = fresh_page()
            page.goto(login_url, wait_until="networkidle")
            page.fill("#username", accounts.ACCOUNTS["required"])
            page.fill("#password", temporary)
            page.click("#kc-login")
            page.wait_for_load_state("networkidle")
            raw = page.locator("#totpSecret").input_value()
            capture.secrets.append(raw)
            capture.take("mfa-enrolment", page, masked=[page.locator("#kc-totp-secret-qr-code")])
            step = totp.time_step()
            page.fill("#totp", totp.totp(totp.keycloak_key(raw), step))
            page.fill("#userLabel", "eko201-required-device")
            page.locator("input[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("networkidle")
            capture.take("required-password", page)
            page.fill("#password-new", updated)
            page.fill("#password-confirm", updated)
            page.locator("input[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("networkidle")
            assert page.url.startswith(app.app_origin(composition)), "login did not reach the app"

            page = fresh_page()
            page.goto(login_url, wait_until="networkidle")
            page.fill("#username", accounts.ACCOUNTS["required"])
            page.fill("#password", updated)
            page.click("#kc-login")
            page.wait_for_load_state("networkidle")
            capture.take("mfa-code", page)
            valid = {totp.totp(totp.keycloak_key(raw), item) for item in range(step - 2, step + 4)}
            wrong = next(code for code in ("000000", "111111", "222222") if code not in valid)
            page.fill("#otp", wrong)
            page.locator("input[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("networkidle")
            capture.take("mfa-code-error", page)
            next_step = max(totp.time_step(), step + 1)
            page.fill("#otp", totp.totp(totp.keycloak_key(raw), next_step))
            page.locator("input[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("networkidle")
            assert page.url.startswith(app.app_origin(composition)), "code login did not finish"
        finally:
            browser.close()

    assert set(capture.pages) == set(accounts.POLISH_MARKERS)
    # One-change contrasts on a captured page: language, the name, one Polish phrase.
    login = capture.pages["login"]
    english = login.replace('lang="pl"', 'lang="en"', 1)
    assert "login: page language is not Polish" in accounts.page_findings("login", english)
    nameless = login.replace("Eko_CRM", "Keycloak")
    assert "login: the Eko_CRM name is missing" in accounts.page_findings("login", nameless)
    replaced = login.replace("Zaloguj się do Eko_CRM", "Sign in to your account")
    found = accounts.page_findings("login", replaced)
    assert any("English default" in item for item in found), found
    if capture.target is not None:
        (capture.target / "states.json").write_text(
            json.dumps(sorted(capture.pages), indent=2) + "\n", encoding="utf-8"
        )
