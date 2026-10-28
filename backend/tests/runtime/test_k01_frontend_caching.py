"""K-01, frontend half: cache headers of `frontend`'s file server through `proxy` (R-02, EKO-1-06).

A browser that reuses a stale SPA document after a deployment asks the new image for the old
hashed bundle, gets 404 by design, and shows a blank page. So the document (for `/` and every
deep link) must be revalidated on each use, while hashed assets, whose names change with their
content, may be cached for good. A missing asset must not be marked cacheable for good.
"""

import re

import pytest

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

HASHED_ASSET = re.compile(r"""(?:src|href)=["'](/assets/[\w.-]+-[\w-]{8,}\.(?:js|css))["']""")
MISSING_ASSET = "/assets/index-r02missing0asset.js"
YEAR_SECONDS = 31536000


def directives(cache_control: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in (cache_control or "").split(","):
        name, _, value = part.strip().partition("=")
        if name:
            parsed[name.lower()] = value
    return parsed


@pytest.mark.parametrize("path", ["/", "/klienci/123/wizyty", "/index.html"])
def test_k01_the_spa_document_is_revalidated_on_every_use(running: Started, path: str) -> None:
    page = running.composition.through_proxy("app", path)
    assert page.status_code == 200
    cache = directives(page.headers.get("cache-control"))
    assert "no-cache" in cache or "no-store" in cache, page.headers.get("cache-control")
    assert "immutable" not in cache


def test_k01_a_hashed_asset_is_cached_for_good(running: Started) -> None:
    composition = running.composition
    referenced = HASHED_ASSET.findall(composition.through_proxy("app", "/").text)
    assert referenced, "no hashed bundle asset referenced"
    asset = composition.through_proxy("app", referenced[0])
    assert asset.status_code == 200
    cache = directives(asset.headers.get("cache-control"))
    assert "immutable" in cache, asset.headers.get("cache-control")
    assert int(cache.get("max-age") or 0) >= YEAR_SECONDS


def test_k01_a_missing_hashed_asset_is_not_cached_for_good(running: Started) -> None:
    missing = running.composition.through_proxy("app", MISSING_ASSET)
    assert missing.status_code == 404
    cache = directives(missing.headers.get("cache-control"))
    assert "immutable" not in cache
    assert "no-cache" in cache or "no-store" in cache, missing.headers.get("cache-control")
