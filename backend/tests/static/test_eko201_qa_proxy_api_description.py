"""EKO-2-01 QA (K-01, ADR-0003-C23): each shared-environment proxy listener denies OpenAPI and
documentation paths itself.

The runtime carrier (`tests/runtime/test_k04_runtime.py`, C23) cannot see this denial on the
application listener: the backend serves its documents outside `/api/` and the listener forwards
only `/api/*` to it, so removing the listener's `import no_api_description` leaves every probed
path without OpenAPI content (QA mutation EKO-2-01/M-89 survived it). This check reads the
listener blocks of `proxy/Caddyfile`: each public site imports the denial inside its `route`
before any `reverse_proxy`, and the denial snippet answers 404 to the documented path pattern.
"""

import re

import pytest

from tests.support.repo import REPO_ROOT

CADDYFILE = REPO_ROOT / "proxy" / "Caddyfile"
PUBLIC_SITES = ("{$APP_HOST}", "{$AUTH_HOST}")


def site_block(text: str, site: str) -> str:
    start = text.index(f"\n{site} {{")
    depth = 0
    for index in range(text.index("{", start + len(site) + 1), len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    raise AssertionError(f"{site}: block not closed")


def violations(text: str) -> list[str]:
    problems: list[str] = []
    snippet = re.search(r"\(no_api_description\) \{(.*?)\n\}", text, re.S)
    if snippet is None:
        return ["no_api_description snippet missing"]
    body = snippet.group(1)
    if "openapi" not in body or "docs" not in body or "redoc" not in body:
        problems.append("no_api_description does not match openapi, docs and redoc")
    if not re.search(r"respond @api_description 404", body):
        problems.append("no_api_description does not answer 404")
    for site in PUBLIC_SITES:
        block = site_block(text, site)
        route = block[block.find("route {") :]
        imported = route.find("import no_api_description")
        proxied = route.find("reverse_proxy")
        if "route {" not in block or imported < 0 or (0 <= proxied < imported):
            problems.append(f"{site}: no_api_description not imported before reverse_proxy")
    return problems


def test_qa_k01_each_public_listener_denies_openapi_and_docs_itself() -> None:
    assert violations(CADDYFILE.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("site", PUBLIC_SITES)
def test_qa_k01_contrast_dropping_one_listener_import_is_named(site: str) -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    block = site_block(text, site)
    changed = text.replace(block, block.replace("\t\timport no_api_description\n", "", 1), 1)
    assert changed != text
    assert violations(changed) == [f"{site}: no_api_description not imported before reverse_proxy"]
