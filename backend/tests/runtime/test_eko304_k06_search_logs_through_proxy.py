"""EKO-3-04 K-06, composition half (ADR-0005 *What may appear in logs*; capability row of ADR-0005's
log content): a rep's search sent through `proxy` with a marker in `q`, and a refused over-long
`q` and `owner` carrying the same marker, leave the marker in no line `backend`, `proxy` or
`postgres` writes, while each request does write its own lines there; each refusal is a 422 that
does not repeat the marker.

The dev profile (`running`) supplies Keycloak, so the rep's requests carry a real session made by
a real login through the proxy. Every value is synthetic (ADR-0005).
"""

import json
import secrets
from typing import Any

import httpx
import pytest

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Started
from tests.runtime.eko113 import window
from tests.runtime.keycloak_client import RealmClient
from tests.support import eko112_fixtures as eko112
from tests.support import eko201_keycloak as accounts
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
MARKER = f"markerk06p{TOKEN}"
CUSTOMERS = "/api/customers"


def rep_session(started: Started) -> str:
    composition = started.composition
    env = composition.env
    master = RealmClient(composition, "master")
    browser = RealmClient(composition, "eko", listener="auth")
    try:
        token = master.direct_master_token(
            eko112.ACCOUNTS["breakglass_one"], env[eko112.PASSWORD_VARIABLES["breakglass_one"]]
        )
        password = "synthetic-" + secrets.token_urlsafe(24)
        app.ensure_staff_account(master, token, "login", password)
        return app.login(composition, browser, accounts.ACCOUNTS["login"], password)
    finally:
        browser.close()
        master.close()


def call(
    started: Started, session: str, method: str, path: str, body: Any = None
) -> httpx.Response:
    env = started.composition.env
    host = env["APP_HOST"]
    url = httpx.URL(
        scheme="https", host="127.0.0.1", port=int(env["PROXY_HTTPS_PORT"]), raw_path=path.encode()
    )
    headers = {"Host": host, "Cookie": f"{app.SESSION_COOKIE}={session}"}
    if method != "GET":
        headers["Origin"] = app.app_origin(started.composition)
    with httpx.Client(verify=False, timeout=30, follow_redirects=False) as client:
        request = client.build_request(method, url, headers=headers, json=body)
        request.extensions["sni_hostname"] = host
        return client.send(request)


def test_k06_a_searched_or_refused_marker_reaches_no_backend_proxy_or_postgres_line(
    running: Started,
) -> None:
    session = rep_session(running)
    made = call(running, session, "POST", CUSTOMERS, {"name": f"Ferma {MARKER}"})
    assert made.status_code == 201, made.text[:300]
    windows = {
        service: window(running.composition, service)
        for service in ("backend", "proxy", "postgres")
    }
    searched = call(running, session, "GET", f"{CUSTOMERS}?q={MARKER}")
    long_query = call(running, session, "GET", f"{CUSTOMERS}?q={MARKER}{'q' * 254}")
    long_owner = call(running, session, "GET", f"{CUSTOMERS}?owner={MARKER}{'o' * 256}")

    assert searched.status_code == 200, searched.text[:300]
    assert [item["id"] for item in searched.json()["items"]] == [made.json()["id"]]
    for refused, parameter in ((long_query, "q"), (long_owner, "owner")):
        assert refused.status_code == 422, refused.text[:300]
        assert [e["loc"] for e in refused.json()["detail"]] == [["query", parameter]]
        assert MARKER not in refused.text

    texts = {service: mark.text(settle=1.5) for service, mark in windows.items()}
    correlation = {r.headers["eko-correlation-id"] for r in (searched, long_query, long_owner)}
    backend_lines, _ = ll.json_lines(texts["backend"])
    written = {
        line.get("correlation_id")
        for line in backend_lines
        if line.get("event") == "request" and line.get("route") == CUSTOMERS
    }
    assert correlation <= written, "a request wrote no backend line: the window would be vacuous"
    proxy_lines, _ = ll.json_lines(texts["proxy"])
    assert len(proxy_lines) >= 3, "the proxy wrote no access line: the window would be vacuous"
    for service, text in texts.items():
        assert ll.leaks(text + json.dumps(text), MARKER) == [], service
