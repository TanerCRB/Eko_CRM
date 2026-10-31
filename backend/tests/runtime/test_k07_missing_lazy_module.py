"""K-07: asset routing never turns a missing JavaScript module into the SPA document."""

import re

import pytest

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

ROOT_ELEMENT = re.compile(r"""<div id=["']root["']""")
JAVASCRIPT_ASSET = re.compile(r"""src=["'](/assets/[\w.-]+-[\w-]{8,}\.js)["']""")
MISSING_ASSET = "/assets/k07-never-existed-0.js"


def test_k07_missing_lazy_module_gets_clean_404_not_spa_document(running: Started) -> None:
    composition = running.composition
    document = composition.through_proxy("app", "/klienci")
    assert document.status_code == 200
    assert ROOT_ELEMENT.search(document.text)

    referenced = JAVASCRIPT_ASSET.findall(composition.through_proxy("app", "/").text)
    assert referenced, "no hashed JavaScript bundle referenced"
    existing = composition.through_proxy("app", referenced[0])
    assert existing.status_code == 200
    assert "javascript" in existing.headers.get("content-type", "")

    missing = composition.through_proxy(
        "app",
        MISSING_ASSET,
        headers={"Accept": "text/javascript, application/javascript, */*"},
    )
    assert missing.status_code == 404
    assert "text/html" not in missing.headers.get("content-type", "")
    assert not ROOT_ELEMENT.search(missing.text)
    assert "<!doctype html>" not in missing.text.lower()
    cache_control = missing.headers.get("cache-control", "").lower()
    assert "immutable" not in cache_control
    assert "no-cache" in cache_control or "no-store" in cache_control
