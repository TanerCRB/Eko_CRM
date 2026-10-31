"""K-06: an open SPA recovers an unloaded lazy destination across frontend replacement."""

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from tests.runtime.conftest import UP_TIMEOUT_SECONDS, Composition
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

DESTINATION = "Klienci"
LAZY_CHUNK = re.compile(rf"{DESTINATION}-[\w-]+\.js")
MISSING_MODULE_ERRORS = (
    "failed to fetch dynamically imported module",
    "error loading dynamically imported module",
    "expected a javascript module script",
)


def lazy_chunk(composition: Composition) -> str | None:
    assets = composition.compose("exec", "-T", "frontend", "ls", "-1", "/srv/assets").stdout
    matches = [name for name in assets.splitlines() if LAZY_CHUNK.fullmatch(name)]
    assert len(matches) <= 1, f"expected at most one {DESTINATION} chunk, got {matches}"
    return f"/assets/{matches[0]}" if matches else None


def build_replacement(
    composition: Composition, directory: Path, old_chunk: str | None
) -> tuple[Composition, str]:
    context = directory / "frontend-new"
    shutil.copytree(
        REPO_ROOT / "frontend",
        context,
        ignore=shutil.ignore_patterns(".env*", "node_modules", "dist", ".vite", "*.tsbuildinfo"),
    )
    main = context / "src" / "main.tsx"
    source = main.read_text(encoding="utf-8")
    assert source.count("mount(document);") == 1
    main.write_text(
        source.replace(
            "mount(document);",
            'document.documentElement.dataset.testBuild = "replacement";\nmount(document);',
        ),
        encoding="utf-8",
    )
    source_tag = f"localhost/eko-crm/frontend-test:{composition.project}-source"
    subprocess.run(
        ["docker", "build", "-q", "-t", source_tag, str(context)],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )
    replacement_tag = source_tag
    if old_chunk is not None:
        replacement_tag = f"localhost/eko-crm/frontend-test:{composition.project}-replacement"
        dockerfile = directory / "Dockerfile.replacement"
        dockerfile.write_text(
            f"FROM {source_tag}\nUSER root\nRUN rm -f /srv{old_chunk}\nUSER nobody\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "docker",
                "build",
                "-q",
                "-t",
                replacement_tag,
                "-f",
                str(dockerfile),
                str(directory),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        subprocess.run(["docker", "rmi", source_tag], check=False, capture_output=True)
    override = directory / "frontend-replacement.yaml"
    override.write_text(
        f"services:\n  frontend:\n    image: {replacement_tag}\n    pull_policy: never\n",
        encoding="utf-8",
    )
    replacement = Composition(
        project=composition.project,
        env_file=composition.env_file,
        extra_files=[override],
    )
    return replacement, replacement_tag


def wait_for_frontend(composition: Composition) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = composition.inspect("frontend")["State"]
        if state.get("Health", {}).get("Status") == "healthy":
            return
        time.sleep(0.5)
    raise AssertionError("replacement frontend did not become healthy within 120 s")


def module_import(page: Page, path: str) -> dict[str, object]:
    result = page.evaluate(
        """async (path) => {
          try {
            await import(path);
            return { failed: false, error: "" };
          } catch (error) {
            return { failed: true, error: String(error) };
          }
        }""",
        path,
    )
    return cast(dict[str, object], result)


def test_k06_open_spa_recovers_unloaded_lazy_chunk_after_frontend_replacement(
    fresh: Composition, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    up = fresh.compose(
        "up",
        "--build",
        "--wait",
        "--wait-timeout",
        str(UP_TIMEOUT_SECONDS),
        "proxy",
        check=False,
        timeout=UP_TIMEOUT_SECONDS + 300,
    )
    assert up.returncode == 0, up.stderr[-6000:]
    old_frontend = fresh.container_id("frontend")
    old_proxy = fresh.container_id("proxy")
    old_backend = fresh.container_id("backend")
    old_chunk = lazy_chunk(fresh)
    env = fresh.env
    app_url = f"https://{env['APP_HOST']}:{env['PROXY_HTTPS_PORT']}"
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
        capture_output=True,
        timeout=600,
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[f"--host-resolver-rules=MAP {env['APP_HOST']} 127.0.0.1"],
        )
        try:
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            requested: list[str] = []
            automatic_navigations: list[str] = []
            page_errors: list[str] = []
            page.on("request", lambda request: requested.append(request.url))
            page.on(
                "framenavigated",
                lambda frame: (
                    automatic_navigations.append(frame.url)
                    if frame == page.main_frame
                    else None
                ),
            )
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(app_url, wait_until="networkidle")
            expect(page.get_by_role("heading", name="Pulpit", exact=True)).to_be_visible()
            page.evaluate("window.__k06OriginalDocument = true")
            if old_chunk is not None:
                requested_paths = {urlsplit(url).path for url in requested}
                assert old_chunk not in requested_paths, "destination chunk loaded initially"
                cached = cast(
                    list[str],
                    page.evaluate(
                        "performance.getEntriesByType('resource').map((entry) => entry.name)"
                    ),
                )
                assert old_chunk not in {urlsplit(url).path for url in cached}

            replacement, replacement_image = build_replacement(fresh, tmp_path, old_chunk)
            request.addfinalizer(
                lambda: subprocess.run(
                    ["docker", "rmi", "-f", replacement_image], check=False, capture_output=True
                )
            )
            replacement.compose(
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                "frontend",
                timeout=300,
            )
            wait_for_frontend(replacement)
            assert replacement.container_id("frontend") != old_frontend
            assert replacement.container_id("proxy") == old_proxy
            assert replacement.container_id("backend") == old_backend
            assert page.evaluate("window.__k06OriginalDocument === true"), (
                "the old document did not remain open until destination activation"
            )
            assert old_chunk is not None, (
                "the old build has no lazy Klienci destination chunk to preserve across deployment"
            )
            never_existed = module_import(page, "/assets/k06-never-existed-0.js")
            assert never_existed["failed"] is True, never_existed
            navigations_before_activation = len(automatic_navigations)
            page.get_by_role("link", name=DESTINATION, exact=True).click()
            try:
                expect(page.get_by_role("heading", name=DESTINATION, exact=True)).to_be_visible(
                    timeout=15_000
                )
            except AssertionError as error:
                raise AssertionError(
                    f"lazy destination failed; browser page errors: {page_errors}"
                ) from error
            assert any(urlsplit(url).path == old_chunk for url in requested), (
                "activation never requested the old build's unloaded destination chunk"
            )
            terminal_errors = [
                error
                for error in page_errors
                if any(marker in error.lower() for marker in MISSING_MODULE_ERRORS)
            ]
            assert not terminal_errors, terminal_errors
            if not page.evaluate("window.__k06OriginalDocument === true"):
                assert len(automatic_navigations) > navigations_before_activation, (
                    "document changed without an observed automatic recovery navigation"
                )
                assert urlsplit(page.url).path == "/klienci"
        finally:
            browser.close()
