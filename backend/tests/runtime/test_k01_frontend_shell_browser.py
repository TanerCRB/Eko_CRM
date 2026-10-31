"""K-01: real-browser shell navigation, focus, responsive and reduced-motion behaviour."""

import re
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

NAVIGATION = "Nawigacja główna"
SECTION = "Pulpit"
SKIP_LINK = "Przejdź do treści"
MENU_NAME = re.compile(r"nawigacj", re.IGNORECASE)


def motion_style(page: Page, selector: str) -> dict[str, str]:
    return cast(
        dict[str, str],
        page.locator(selector).evaluate(
            """(element) => {
              const style = getComputedStyle(element);
              return {
                animationName: style.animationName,
                animationDuration: style.animationDuration,
                transitionDuration: style.transitionDuration,
              };
            }"""
        ),
    )


def test_k01_shell_navigation_focus_responsive_boundary_and_reduced_motion(
    running: Started, chromium_executable: Path
) -> None:
    composition = running.composition
    env = composition.env
    app_url = f"https://{env['APP_HOST']}:{env['PROXY_HTTPS_PORT']}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[f"--host-resolver-rules=MAP {env['APP_HOST']} 127.0.0.1"],
        )
        try:
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 701, "height": 900},
                reduced_motion="no-preference",
            )
            page = context.new_page()
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
                style = motion_style(page, selector)
                assert style["animationName"] == "none", (selector, style)
                assert set(style["animationDuration"].split(", ")) == {"0s"}, (selector, style)
                assert set(style["transitionDuration"].split(", ")) == {"0s"}, (selector, style)
            context.close()
        finally:
            browser.close()
