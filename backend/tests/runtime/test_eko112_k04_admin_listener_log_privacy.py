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

Hardening 2026-11-11 (CI run 42897088542, Issue #126): this was the only eko112 test red in
the build-mode runtime job and one of the two reds shared by BOTH runtime jobs on ubuntu,
while green standalone-cold twice on the Docker Desktop development host — the host split the
EKO-1-12/qa2-3 finding (F-04) names: `compose restart proxy` returns when the container has
STARTED, not when Caddy has bound the configuration the entrypoint selected, and a one-shot
listener probe inside that window reads a refused connection as a closed gate. On the fast
runner socket path the probe reliably loses the race; the Desktop round-trip hides it. This
file was the only member of the family still asserting straight after the restart; every wait
now follows the hardened siblings (`wait_for_proxy_running`, `wait_for_serving` — the budgets
those files proved green on the same ubuntu runners), the access-line read is a bounded poll
over the settle the c4 proxy-log tests proved sufficient, and every assertion failure carries
a phase note (container state, marker-versus-boot comparisons, proxy log tail as field names)
so a future red explains itself in CI. The note names states and field names, never line
values: the unrestricted shape this test exists to catch is exactly a line whose uri value
carries the authorization code.
"""

import base64
import hashlib
import html
import json
import secrets
import subprocess
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.runtime.conftest import Composition
from tests.runtime.eko113 import window
from tests.runtime.keycloak_client import (
    FORM_ACTION,
    RealmClient,
    boot_identity,
    listener_open,
)
from tests.runtime.lab import docker
from tests.runtime.test_eko112_k02_marker_boot_binding import wait_for_proxy_running
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import (
    assert_connection_death,
    wait_for_serving,
)
from tests.support import eko112_fixtures as fixtures
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime
CONSOLE_PATH = "/admin/master/console/"
# What a diagnostic may swallow: docker/CLI/process failures and shape slips in inspected
# JSON. A diagnostic must never mask the assertion it annotates, so it catches this list,
# never a bare Exception (BLE001 is a deliberate part of the repository's lint set).
DIAGNOSTIC_ERRORS = (
    subprocess.SubprocessError,
    OSError,
    ValueError,
    KeyError,
    AssertionError,
    AttributeError,
    TypeError,
)


def phase_note(composition: Composition) -> str:
    """One line describing the phase for assertion failures, built only on failure.

    Container state, boolean marker-versus-current-boot comparisons and the proxy log tail
    reduced to field names: none of these carry a request value, so a failure message cannot
    echo the very material the criterion forbids (the unrestricted shape leaks the code in
    `request.uri`, and log lines are exactly what a diagnostic is tempted to print raw)."""
    try:
        state = composition.inspect("proxy")["State"]
        identity = boot_identity(composition)
        parts = [
            f"proxy running={state.get('Running')} status={state.get('Status')} "
            f"exit={state.get('ExitCode')}",
            f"boot identity observed={bool(identity)}",
        ]
        for gate in ("admin", "public"):
            marker = composition.compose(
                "exec",
                "-T",
                "proxy",
                "sh",
                "-c",
                f"cat /data/{gate}-open 2>/dev/null || true",
                check=False,
                timeout=60,
            ).stdout.strip()
            parts.append(
                f"{gate} marker present={bool(marker)} "
                f"names_current_boot={bool(marker) and marker == identity}"
            )
        parts.append(f"proxy log tail field names: {_proxy_tail_shape(composition)}")
        return "phase: " + "; ".join(parts)
    except DIAGNOSTIC_ERRORS:  # a diagnostic must never replace the failure it explains
        return "phase: state unavailable"


def _proxy_tail_shape(composition: Composition, lines: int = 12) -> str:
    """The last proxy log lines as JSON field names (non-JSON lines counted, not quoted).

    `docker logs` raw, the same reader the window itself uses: `compose logs` prefixes every
    line with the container name, which would render all shapes as unparseable text."""
    try:
        container = composition.container_id("proxy")
        logs = docker("logs", "--tail", str(lines), container, check=False, timeout=60)
    except DIAGNOSTIC_ERRORS:
        return "proxy log unreadable"
    shapes: list[str] = []
    for raw in (logs.stdout + logs.stderr).splitlines()[-lines:]:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except ValueError:
            shapes.append(f"<non-json {len(stripped)} chars>")
            continue
        if isinstance(parsed, dict):
            shapes.append(",".join(sorted(ll.flatten(parsed))))
        else:
            shapes.append("<non-object json>")
    return " | ".join(shapes)


def console_access_lines(text: str) -> list[dict[str, Any]]:
    """The completed access lines for the console redirect: GET on the console path."""
    objects, _ = ll.json_lines(text)
    return [
        line
        for line in objects
        if ll.flatten(line).get("request.uri", "").startswith(CONSOLE_PATH)
        and str(ll.flatten(line).get("request.method", "")) == "GET"
        and "size" in line
    ]


def _wait_proxy_running_note(composition: Composition) -> None:
    """`wait_for_proxy_running` with the phase note appended to its failure."""
    try:
        wait_for_proxy_running(composition)
    except AssertionError as error:
        raise AssertionError(f"{error} | {phase_note(composition)}") from error


def _wait_admin_serving_note(composition: Composition, deadline_seconds: int = 90) -> int:
    """`wait_for_serving` with the phase note appended to its failure."""
    try:
        return wait_for_serving(composition, "admin", deadline_seconds=deadline_seconds)
    except AssertionError as error:
        raise AssertionError(f"{error} | {phase_note(composition)}") from error


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
        assert page.status_code == 200, (
            f"login page status {page.status_code} | {phase_note(composition)}"
        )
        match = FORM_ACTION.search(page.text)
        assert match is not None, f"login form not found | {phase_note(composition)}"
        parsed = urlparse(html.unescape(match.group(1)))
        submitted = client.request(
            "POST",
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            data={
                "username": fixtures.ACCOUNTS["breakglass_one"],
                "password": composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
            },
        )
        assert submitted.status_code in (302, 303), (
            f"login status {submitted.status_code} | {phase_note(composition)}"
        )
        location = submitted.headers.get("location", "")
        location_parts = urlparse(location)
        assert location_parts.path == CONSOLE_PATH, (
            f"unexpected redirect path {location_parts.path} | {phase_note(composition)}"
        )
        code = parse_qs(location_parts.query).get("code", [""])[0]
        assert code, (
            f"the login returned no authorization code to carry | {phase_note(composition)}"
        )
        final = client.request("GET", location_parts.path + "?" + location_parts.query)
        assert final.status_code in (200, 302), (
            f"console redirect status {final.status_code} | {phase_note(composition)}"
        )
        raw = location_parts.path + "?" + location_parts.query
        return raw, code
    finally:
        client.close()


def test_k04_admin_only_window_logs_the_console_redirect_restricted(fresh: Composition) -> None:
    from tests.runtime.keycloak_client import prepare, run_bootstrap

    prepare(fresh)
    run_bootstrap(fresh)
    # Both asserts are preceded by the bootstrap's own in-container wget verification of
    # each listener (open_gate), so they name a state the script just proved, not a race.
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")

    # Enter the admin-only window: exactly the state entrypoint selects during a bootstrap
    # that has opened the admin gate but not yet the public one.
    fresh.compose("exec", "-T", "proxy", "rm", "-f", "/data/public-open")
    fresh.compose("restart", "proxy")
    # The qa2-3/F-04 hardening every sibling carries: `compose restart` returns at container
    # start; wait for the container, then for the listener to actually answer, before any
    # state assertion — on the runners the first one-shot probe landed in that window and a
    # refused connection read as the gate closing inside its own open window.
    _wait_proxy_running_note(fresh)
    admin_status = _wait_admin_serving_note(fresh)
    assert admin_status == 200, (
        f"the admin listener answered {admin_status} in its own open window | {phase_note(fresh)}"
    )
    assert listener_open(fresh, "admin"), (
        f"the admin listener closed in its own open window | {phase_note(fresh)}"
    )
    # With the entrypoint demonstrably bound, the public listener's silence is now the
    # admin-only configuration's own choice, not the restart window's nothing-bound-yet.
    assert_connection_death(fresh, "auth")

    log = window(fresh, "proxy")
    raw_path, code = console_login_over_admin_listener(fresh)
    assert code not in ("",)  # sanity: the probe carries a value to look for
    text = log.text(settle=2.0)
    # The c4 proxy-log family proved the flush settles in about a second on these runners;
    # the bound is the sibling poll budget, not a guess — it covers a late flush instead of
    # asserting against a snapshot taken too early.
    deadline = time.monotonic() + 90.0
    while not console_access_lines(text) and time.monotonic() < deadline:
        text = log.text(settle=2.0)
    assert console_access_lines(text), (
        f"no access line for the console redirect within the poll window | {phase_note(fresh)}"
    )
    # One final settled read: late-flushed lines of this window must not escape the leak scan.
    text = log.text(settle=2.0)

    # 1. The code value appears nowhere in the proxy's own output for this window.
    assert ll.leaks(text, code) == [], (
        f"the proxy logged the authorization code value | {phase_note(fresh)}"
    )
    assert ll.leaks(text, "code=") == [], (
        f"a logged line kept the code query parameter | {phase_note(fresh)}"
    )

    # 2. The request's access line exists and is the documented restricted form.
    access = console_access_lines(text)
    assert access, "the access line vanished between the poll and the settled read | " + phase_note(
        fresh
    )
    for line in access:
        flat = ll.flatten(line)
        logged_uri = str(flat["request.uri"])
        assert flat["request.uri"] == CONSOLE_PATH, (
            "the logged uri kept its query string (value withheld; "
            f"{len(logged_uri)} chars, has_query={'?' in logged_uri}) | {phase_note(fresh)}"
        )
        assert "request.remote_ip" not in flat, (
            f"the admin window logged the remote address | {phase_note(fresh)}"
        )
        assert "request.headers" not in flat, (
            f"the admin window logged request headers | {phase_note(fresh)}"
        )
        problems = ll.proxy_line_problems(line, "proxy.access")
        # `proxy_line_problems` quotes the uri it rejects: under the unrestricted shape that
        # value is the very code this criterion forbids echoing, so it is redacted here.
        problems_text = "; ".join(problems).replace(code, "<redacted>")
        assert problems == [], (
            f"the access line is not the documented restricted form: {problems_text} | "
            f"{phase_note(fresh)}"
        )
