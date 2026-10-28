"""K-01, frontend half: what `frontend`'s own file server answers through `proxy` (QA, EKO-1-06).

K-01 asserts that `/` loads the built SPA and one hashed asset. These tests pin the two routing
rules of `frontend/Caddyfile` that `/` alone never exercises, and the image's non-root user:

- a client-side route (a deep link) gets the SPA page, not a 404;
- a hashed asset that does not exist is a 404, never the SPA page with 200 (a stale bundle must
  fail loudly), while the asset the page references is a 200 (the contrast);
- the static file server does not run as root.
"""

import re

import pytest

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

ROOT_ELEMENT = re.compile(r"""<div id=["']root["']""")
HASHED_ASSET = re.compile(r"""(?:src|href)=["'](/assets/[\w.-]+-[\w-]{8,}\.(?:js|css))["']""")
MISSING_ASSET = "/assets/index-qa0missing0asset.js"
DEEP_LINK = "/klienci/123/wizyty"


def test_k01_a_deep_link_gets_the_spa_page(running: Started) -> None:
    page = running.composition.through_proxy("app", DEEP_LINK)
    assert page.status_code == 200
    assert ROOT_ELEMENT.search(page.text)


def test_k01_a_missing_hashed_asset_is_404_while_the_referenced_one_is_200(
    running: Started,
) -> None:
    composition = running.composition
    referenced = HASHED_ASSET.findall(composition.through_proxy("app", "/").text)
    assert referenced, "no hashed bundle asset referenced"
    # Contrast: the same directory, the same kind of name; only existence differs.
    assert composition.through_proxy("app", referenced[0]).status_code == 200
    missing = composition.through_proxy("app", MISSING_ASSET)
    assert missing.status_code == 404
    assert not ROOT_ELEMENT.search(missing.text)


def test_k01_frontend_file_server_does_not_run_as_root(running: Started) -> None:
    uid = running.composition.compose("exec", "-T", "frontend", "id", "-u").stdout.strip()
    assert uid.isdigit(), uid
    assert uid != "0"
