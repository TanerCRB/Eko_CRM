"""EKO-2-02 K-02 (ADR-0003-C6, *Roles*): roles come only from the verified token. A role named in
a header, the query, the body or a cookie other than the session cookie changes no answer and no
identity received inward.

A `rep` session (a real login through the local OIDC stub) calls the probe injected onto the
shipped `create_app()`: its customers-reading GET carries a `role` query field and its
customers-changing POST a `role` body field, so each channel reaches a live route.
"""

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.runtime.eko201 import conftest as eko201
from tests.runtime.eko201.conftest import AppFactory, Browser
from tests.support import eko202_probe as probe
from tests.support import oidc_stub

pytestmark = pytest.mark.runtime

# EKO-2-01's carrier fixtures (real PostgreSQL, the OIDC stub, the shipped `create_app()`), bound
# here by name because they live in a sibling directory's conftest.
pg = eko201.pg
clean = eko201.clean
stub = eko201.stub
clock = eko201.clock
make_app = eko201.make_app
browser_for = eko201.browser_for

CHANNELS = ("header", "query", "body", "cookie")
VALUES: dict[str, Any] = {
    "manager": "manager",
    "case-variant": "Manager",
    "list": ["manager", "administrator"],
    "duplicated": ["manager", "manager"],
    "empty": "",
    "null": None,
    "empty-list": [],
}


def injected(channel: str, value: Any) -> dict[str, Any]:
    """Request arguments naming `value` as a role in one channel."""
    many = value if isinstance(value, list) else [value]
    text = "" if value is None else ",".join(str(v) for v in many)
    if channel == "header":
        return {"headers": {"X-Role": text, "Role": text, "X-Roles": text}}
    if channel == "query":
        return {"params": [("role", "" if v is None else str(v)) for v in many] or [("role", "")]}
    if channel == "body":
        return {"body": {"role": value}}
    return {"cookies": {"role": text, "roles": text}}


def merged(channels: tuple[str, ...], value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for channel in channels:
        out.update(injected(channel, value))
    return out


def send(browser: Browser, method: str, path: str, extra: dict[str, Any]) -> httpx.Response:
    """One request; a body is JSON (also on GET, where no handler reads it), extra cookies are
    sent beside the session cookie for this request only."""
    saved = dict(browser.jar)
    browser.jar.update(extra.get("cookies", {}))
    headers = dict(extra.get("headers", {}))
    content = None
    if "body" in extra or method == "POST":
        headers["content-type"] = "application/json"
        content = json.dumps(extra.get("body", {}))
    try:
        return browser.send(
            method, path, headers=headers, params=extra.get("params"), content=content
        )
    finally:
        browser.jar.clear()
        browser.jar.update(saved)


def logged_in(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, roles: list[str]
) -> tuple[FastAPI, probe.Recorder, Browser]:
    app = make_app()
    recorder = probe.install_probe(app)
    stub.access_overrides = probe.role_claims(client=roles)
    browser = browser_for(app)
    browser.login()
    assert browser.session is not None
    return app, recorder, browser


def answer(response: httpx.Response) -> tuple[int, Any]:
    return response.status_code, response.json()


@pytest.mark.parametrize("value", sorted(VALUES))
@pytest.mark.parametrize("channels", [(c,) for c in CHANNELS] + [CHANNELS], ids=[*CHANNELS, "all"])
def test_k02_role_named_by_the_client_changes_no_answer_and_no_identity(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    channels: tuple[str, ...],
    value: str,
) -> None:
    from app.domain.caller import Role

    _, recorder, browser = logged_in(make_app, browser_for, stub, ["rep"])
    plain_read = answer(send(browser, "GET", probe.CUSTOMERS, {}))
    plain_change = answer(send(browser, "POST", probe.CUSTOMERS, {}))
    plain_team = answer(send(browser, "GET", probe.TEAM, {}))
    assert plain_read[0] == plain_change[0] == 200
    assert plain_team[0] == 403

    extra = merged(channels, VALUES[value])
    read = answer(send(browser, "GET", probe.CUSTOMERS, extra))
    change = answer(send(browser, "POST", probe.CUSTOMERS, extra))
    team = answer(send(browser, "GET", probe.TEAM, extra))
    assert (read, change, team) == (plain_read, plain_change, plain_team)
    assert recorder.received, "nothing crossed inward"
    assert {caller.roles for caller in recorder.received} == {frozenset({Role.REP})}


def test_k02_contrast_the_token_claim_naming_manager_is_honoured(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    from app.domain.caller import Role

    _, recorder, browser = logged_in(make_app, browser_for, stub, ["rep", "manager"])
    assert send(browser, "GET", probe.TEAM, {}).status_code == 200
    assert send(browser, "GET", probe.CUSTOMERS, {}).status_code == 200
    assert {caller.roles for caller in recorder.received} == {frozenset({Role.REP, Role.MANAGER})}
