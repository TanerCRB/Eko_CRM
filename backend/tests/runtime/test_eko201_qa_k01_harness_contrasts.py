"""QA, EKO-2-01 fix round 3: contrasts for the k01 carrier's harness against the live browser.

The k01 carrier (`test_k01_frontend_shell_browser.py`) now logs in before it reaches the shell
and checks reduced motion on every element a selector matches. These contrasts show, on the
same session-wide `running` composition and with the k01 module's own helpers, that neither
change can pass vacuously:

1. Login is load-bearing: the same application load without `browser_login` ends on
   Keycloak's form with no main navigation, so k01's shell assertions cannot pass on a login
   that silently did not happen.
2. `browser_login` fails loudly instead of landing elsewhere: wrong credentials, and a second
   login on an account whose OTP credential is already enrolled (the reuse k01's account key
   relies on not happening), both raise.
3. The per-element reduced-motion check reaches every match live: `.nav-link` matches the
   destination link and the logout button; under `no-preference` the check fails (the live
   CSS transitions them); under `reduce` it passes; a transition forced on the logout button
   alone (a test-side style on the second match) fails it while the first match alone still
   passes; a selector with no match fails.

Uses its own invented account (`eko201-rotation`), never k01's `eko201-shell`, so k01's OTP
enrolment stays the first on its account whatever the order. Synthetic data only.
"""

from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Started
from tests.runtime.test_k01_frontend_shell_browser import assert_reduced_motion, motion_styles

pytestmark = pytest.mark.runtime

NAVIGATION = "Nawigacja główna"
ACCOUNT = "Konto"
LOGOUT = "Wyloguj się"
KEY = "rotation"
LOGOUT_ONLY_TRANSITION = ".profile-logout { transition: background 1s !important; }"


def test_qa_k01_login_is_load_bearing_and_reduced_motion_check_reaches_every_match(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    origin = app.app_origin(composition)
    auth_host = composition.env["AUTH_HOST"]
    username, password = app.provision_browser_account(composition, KEY)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[app.browser_host_rules(composition)],
        )
        try:
            # 1. Contrast to k01's login: the same load, no login -> Keycloak, no shell.
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.goto(origin, wait_until="networkidle")
            page.wait_for_url(
                lambda url: urlsplit(url).hostname == auth_host, timeout=app.BROWSER_TIMEOUT_MS
            )
            expect(page.get_by_role("navigation", name=NAVIGATION)).to_have_count(0)
            context.close()

            # 2a. Wrong credentials: browser_login raises, it does not land anywhere quietly.
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            with pytest.raises(AssertionError, match="no OTP enrolment demanded"):
                app.browser_login(page, composition, username, password + "-wrong")
            expect(page.get_by_role("navigation", name=NAVIGATION)).to_have_count(0)
            context.close()

            # 3. A real login, then the reduced-motion check against the live CSS.
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 701, "height": 900},
                reduced_motion="no-preference",
            )
            page = context.new_page()
            app.browser_login(page, composition, username, password)
            page.goto(origin, wait_until="networkidle")
            expect(
                page.get_by_role("region", name=ACCOUNT).get_by_role("button", name=LOGOUT)
            ).to_have_count(1)

            styles = motion_styles(page, ".nav-link")
            assert len(styles) >= 2, f".nav-link matched {len(styles)} element(s)"
            with pytest.raises(AssertionError):
                assert_reduced_motion(".nav-link", styles)

            page.emulate_media(reduced_motion="reduce")
            assert_reduced_motion(".nav-link", motion_styles(page, ".nav-link"))

            page.add_style_tag(content=LOGOUT_ONLY_TRANSITION)
            styles = motion_styles(page, ".nav-link")
            assert styles[-1]["transitionDuration"] == "1s", styles
            # What the pre-round-3 single-element read would have seen: still passes.
            assert_reduced_motion(".nav-link", styles[:1])
            with pytest.raises(AssertionError):
                assert_reduced_motion(".nav-link", styles)

            with pytest.raises(AssertionError, match="no element matched"):
                assert_reduced_motion(".qa-no-such", motion_styles(page, ".qa-no-such"))
            context.close()

            # 2b. A second login on the now-enrolled account raises: browser_login shows a
            # reused account key loudly (the code page, not the enrolment page).
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            with pytest.raises(AssertionError, match="no OTP enrolment demanded"):
                app.browser_login(page, composition, username, password)
            context.close()
        finally:
            browser.close()
