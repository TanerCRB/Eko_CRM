"""K-01: real-browser shell navigation, focus, responsive and reduced-motion behaviour."""

import re
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

NAVIGATION = "Nawigacja główna"
SECTION = "Pulpit"
SKIP_LINK = "Przejdź do treści"
ACCOUNT = "Konto"
LOGOUT = "Wyloguj się"
MENU_NAME = re.compile(r"nawigacj", re.IGNORECASE)


def motion_styles(page: Page, selector: str) -> list[dict[str, str]]:
    """The motion properties of every element matching `selector`, in document order (since
    EKO-2-01 the logout button shares the `.nav-link` class with the navigation links)."""
    return cast(
        list[dict[str, str]],
        page.locator(selector).evaluate_all(
            """(elements) => elements.map((element) => {
              const style = getComputedStyle(element);
              return {
                animationName: style.animationName,
                animationDuration: style.animationDuration,
                transitionDuration: style.transitionDuration,
              };
            })"""
        ),
    )


def assert_reduced_motion(selector: str, styles: list[dict[str, str]]) -> None:
    """The original three reduced-motion assertions, applied to each matched element; an empty
    match fails instead of passing vacuously."""
    assert styles, f"{selector}: no element matched"
    for index, style in enumerate(styles):
        assert style["animationName"] == "none", (selector, index, style)
        assert set(style["animationDuration"].split(", ")) == {"0s"}, (selector, index, style)
        assert set(style["transitionDuration"].split(", ")) == {"0s"}, (selector, index, style)


def test_k01_shell_navigation_focus_responsive_boundary_and_reduced_motion(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    env = composition.env
    app_url = f"https://{env['APP_HOST']}:{env['PROXY_HTTPS_PORT']}"
    # EKO-2-01: the whole application requires login, so the shell is reached only after a
    # real login on Keycloak's form (the same way as the EKO-2-01 K-03 browser carrier).
    username, password = app.provision_browser_account(composition, "shell")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[app.browser_host_rules(composition)],
        )
        try:
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 701, "height": 900},
                reduced_motion="no-preference",
            )
            page = context.new_page()
            app.browser_login(page, composition, username, password)
            page.goto(app_url, wait_until="networkidle")
            navigation = page.get_by_role("navigation", name=NAVIGATION)
            destination = navigation.get_by_role("link", name=SECTION, exact=True)
            menu = page.get_by_role("button", name=MENU_NAME)
            skip = page.get_by_role("link", name=SKIP_LINK, exact=True)

            expect(navigation).to_be_visible()
            expect(menu).to_be_hidden()
            expect(navigation.get_by_role("link")).to_have_count(1)
            expect(destination).to_have_attribute("aria-current", "page")
            expect(navigation.locator("[aria-current='page']")).to_have_count(1)
            expect(page.locator("header").get_by_text(SECTION, exact=True)).to_be_visible()

            page.keyboard.press("Tab")
            expect(skip).to_be_focused()
            expect(skip).to_have_attribute("href", "#main")
            page.keyboard.press("Enter")
            expect(page.locator("#main")).to_be_focused()

            page.goto(app_url, wait_until="networkidle")
            page.keyboard.press("Tab")
            expect(skip).to_be_focused()
            page.keyboard.press("Tab")
            expect(destination).to_be_focused()

            page.set_viewport_size({"width": 700, "height": 900})
            page.goto(app_url, wait_until="networkidle")
            expect(menu).to_be_visible()
            expect(menu).to_have_attribute("aria-expanded", "false")
            expect(navigation).to_be_hidden()
            page.keyboard.press("Tab")
            expect(skip).to_be_focused()
            page.keyboard.press("Tab")
            expect(menu).to_be_focused()

            menu.click()
            expect(menu).to_have_attribute("aria-expanded", "true")
            expect(navigation).to_be_visible()
            # The account region at the foot of the sidebar (EKO-2-01, P2 profile placement) is
            # now the navigation's last focusable element.
            page.keyboard.press("Shift+Tab")
            expect(
                page.get_by_role("region", name=ACCOUNT).get_by_role("button", name=LOGOUT)
            ).to_be_focused()
            page.keyboard.press("Shift+Tab")
            expect(destination).to_be_focused()
            page.keyboard.press("Escape")
            expect(menu).to_have_attribute("aria-expanded", "false")
            expect(navigation).to_be_hidden()

            menu.click()
            expect(menu).to_have_attribute("aria-expanded", "true")
            destination.click()
            expect(menu).to_have_attribute("aria-expanded", "false")
            expect(navigation).to_be_hidden()
            expect(navigation.locator("[aria-current='page']")).to_have_count(1)
            expect(destination).to_have_attribute("aria-current", "page")

            page.emulate_media(reduced_motion="reduce")
            for selector in (".sidebar", ".nav-link", ".menu-button"):
                assert_reduced_motion(selector, motion_styles(page, selector))
            context.close()
        finally:
            browser.close()
