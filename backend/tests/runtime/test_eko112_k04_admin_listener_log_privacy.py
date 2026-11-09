"""EKO-1-12 K-04 (log privacy, ADR-0005 addendum 2026-11-02 C4): the admin-only Caddyfile
logs the same restricted line as the full configuration's admin site.

R-01 (reviewer) / G-01 destination: while only the admin gate is open, `proxy/entrypoint.sh`
selects `Caddyfile.admin`. A master-realm console login completed over that listener ends in
`GET /admin/master/console/?code=<nonce>&state=…` — the authorization code is exactly the
material C4 forbids in a log line, together with the remote address. This test brings the
composition into the admin-only window, performs the login, and inspects the proxy's own log
lines for that request: the code value must appear nowhere, the logged `request.uri` must
carry no query string, and the line must match the documented restricted access form
(`tests/support/log_lines.py`, the same rules the full-configuration C4 checks use).

The companion static check `tests/static/test_eko112_k04_caddy_admin_log_parity.py` fails on
the directive drift; this test proves it at the wire. Before `Caddyfile.admin` carried the
`log default` restriction and `import access_log`, this test failed with Caddy's unrestricted
default line (full URI with the query, remote address, headers).
"""

import base64
import hashlib
import html
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.runtime.conftest import Composition
from tests.runtime.eko113 import window
from tests.runtime.keycloak_client import FORM_ACTION, RealmClient, listener_open
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import assert_connection_death
from tests.support import eko112_fixtures as fixtures
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime
CONSOLE_PATH = "/admin/master/console/"


def console_login_over_admin_listener(composition: Composition) -> tuple[str, str]:
    """A successful master-realm console login over the admin listener.

    Returns (raw final request path with its query, authorization code). The code value is
    the probe material: the assertions name its absence, never the value itself.
    """
    env = composition.env
    redirect = f"https://{env['AUTH_ADMIN_HOST']}:{env['PROXY_ADMIN_PORT']}{CONSOLE_PATH}"
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    query = httpx.QueryParams(
        {
            "client_id": "security-admin-console",
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid",
            "state": "eko112-admin-log-probe",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    client = RealmClient(composition, "master", listener="admin")
    try:
        page = client.request("GET", f"/realms/master/protocol/openid-connect/auth?{query}")
        assert page.status_code == 200, f"login page status {page.status_code}"
        match = FORM_ACTION.search(page.text)
        assert match is not None, "login form not found"
        parsed = urlparse(html.unescape(match.group(1)))
        submitted = client.request(
            "POST",
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            data={
                "username": fixtures.ACCOUNTS["breakglass_one"],
                "password": composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
            },
        )
        assert submitted.status_code in (302, 303), f"login status {submitted.status_code}"
        location = submitted.headers.get("location", "")
        location_parts = urlparse(location)
        assert location_parts.path == CONSOLE_PATH, (
            f"unexpected redirect path {location_parts.path}"
        )
        code = parse_qs(location_parts.query).get("code", [""])[0]
        assert code, "the login returned no authorization code to carry"
        final = client.request("GET", location_parts.path + "?" + location_parts.query)
        assert final.status_code in (200, 302), f"console redirect status {final.status_code}"
        raw = location_parts.path + "?" + location_parts.query
        return raw, code
    finally:
        client.close()


def test_k04_admin_only_window_logs_the_console_redirect_restricted(fresh: Composition) -> None:
    from tests.runtime.keycloak_client import prepare, run_bootstrap

    prepare(fresh)
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")

    # Enter the admin-only window: exactly the state entrypoint selects during a bootstrap
    # that has opened the admin gate but not yet the public one.
    fresh.compose("exec", "-T", "proxy", "rm", "-f", "/data/public-open")
    fresh.compose("restart", "proxy")
    assert listener_open(fresh, "admin"), "the admin listener closed in its own open window"
    assert_connection_death(fresh, "auth")

    log = window(fresh, "proxy")
    raw_path, code = console_login_over_admin_listener(fresh)
    assert code not in ("",)  # sanity: the probe carries a value to look for
    text = log.text(settle=2.0)

    # 1. The code value appears nowhere in the proxy's own output for this window.
    assert ll.leaks(text, code) == [], "the proxy logged the authorization code value"
    assert ll.leaks(text, "code=") == [], "a logged line kept the code query parameter"

    # 2. The request's access line exists and is the documented restricted form.
    objects, others = ll.json_lines(text)
    mine = [
        line
        for line in objects
        if ll.flatten(line).get("request.uri", "").startswith(CONSOLE_PATH)
        and str(ll.flatten(line).get("request.method", "")) == "GET"
    ]
    access = [line for line in mine if "size" in line]
    assert access, f"no access line for the console redirect: others={others[:3]} mine={mine[:3]}"
    for line in access:
        flat = ll.flatten(line)
        assert flat["request.uri"] == CONSOLE_PATH, (
            f"the logged uri kept its query string: {flat['request.uri']}"
        )
        assert "request.remote_ip" not in flat, "the admin window logged the remote address"
        assert "request.headers" not in flat, "the admin window logged request headers"
        assert ll.proxy_line_problems(line, "proxy.access") == []
