"""EKO-1-12 D-5: independently executed unknown-username privacy result.

The first test mirrors the accepted D-5 exception on its own path: the unknown typed
username is permitted only at application-realm `LOGIN_ERROR` → `details.username`.
The second test exercises the destination the accepted text keeps prohibited — the master
realm — through the admin listener's console login: an unknown-account typed username and
the event's own top-level session identifier must be absent from every stored master-realm
event, while the known-account verification carrier from the bootstrap (an existing account,
governed by the base rule) keeps its username, so the check cannot pass through
indiscriminate removal or an empty store.
"""

import base64
import hashlib
import html
import secrets
import time
from urllib.parse import urlparse

import httpx
import pytest

from tests.runtime.conftest import Composition, Started
from tests.runtime.keycloak_client import (
    FORM_ACTION,
    RealmClient,
    TypedUsernameStop,
    keycloak_logs,
    matching_value_paths,
)
from tests.runtime.test_eko112_k04_reset_and_log_privacy import (
    assert_refused_login,
    ensure_account,
)
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime


def test_eko112_unknown_username_d5(keycloak_running: Started) -> None:
    composition = keycloak_running.composition
    app = RealmClient(composition, "eko", listener="auth")
    admin = RealmClient(composition, "eko")
    master = RealmClient(composition, "master")
    password = secrets.token_urlsafe(32)
    wrong_password = secrets.token_urlsafe(32)
    try:
        administrator_token = admin.browser_token(
            fixtures.ACCOUNTS["administrator"],
            composition.env[fixtures.PASSWORD_VARIABLES["administrator"]],
            client_id="eko-backend",
            client_secret=composition.env["OIDC_CLIENT_SECRET"],
        )["access_token"]
        ensure_account(
            admin,
            administrator_token,
            fixtures.ACCOUNTS["known"],
            fixtures.ADDRESSES["known"],
            password,
            True,
        )
        assert_refused_login(app, fixtures.ACCOUNTS["known"], wrong_password)
        for marker in fixtures.UNKNOWN_MARKERS:
            assert_refused_login(app, marker, wrong_password)
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        events = master.admin_json(breakglass, "GET", "events", realm="eko")
        logs = keycloak_logs(keycloak_running)
        known_username = fixtures.ACCOUNTS["known"].casefold()
        assert any(
            event["type"] == "LOGIN_ERROR"
            and event.get("details", {}).get("username", "").casefold() == known_username
            for event in events
        ), "known-account contrast did not retain the username"
        for marker in fixtures.UNKNOWN_MARKERS:
            candidates = {marker.casefold(), marker.strip().casefold()}
            allowed_matches = []
            for event in events:
                for path in matching_value_paths(event, candidates):
                    if event["type"] == "LOGIN_ERROR" and path == "details.username":
                        allowed_matches.append(path)
                    else:
                        raise TypedUsernameStop(
                            "D-5 STOP: unknown typed username matched outside application-realm "
                            "LOGIN_ERROR details.username"
                        )
            if matching_value_paths(logs, candidates, "container-log"):
                raise TypedUsernameStop(
                    "D-5 STOP: unknown typed username matched the Keycloak container log"
                )
            assert allowed_matches, "unknown-account stored-event contrast is empty"
    finally:
        app.close()
        admin.close()
        master.close()


def refused_master_console_login(composition: Composition, username: str) -> None:
    """One master-realm console login attempt for `username` over the admin listener.

    The flow is the one the bootstrap's own carrier uses (security-admin-console, PKCE,
    redirect to the admin console). For an account that does not exist it must end on the
    error page — no code redirect — so the attempt is provably an unknown-account LOGIN_ERROR
    producer in the master realm.
    """
    env = composition.env
    redirect = f"https://{env['AUTH_ADMIN_HOST']}:{env['PROXY_ADMIN_PORT']}/admin/master/console/"
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    query = httpx.QueryParams(
        {
            "client_id": "security-admin-console",
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid",
            "state": "eko112-master-d5",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    client = RealmClient(composition, "master", listener="admin")
    try:
        page = client.request("GET", f"/realms/master/protocol/openid-connect/auth?{query}")
        assert page.status_code == 200, f"master login page status {page.status_code}"
        match = FORM_ACTION.search(page.text)
        assert match is not None, "master login form not found"
        parsed = urlparse(html.unescape(match.group(1)))
        submitted = client.request(
            "POST",
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            data={"username": username, "password": "synthetic-" + secrets.token_urlsafe(24)},
        )
        assert submitted.status_code in (200, 401), (
            f"unknown-account master login unexpectedly redirected ({submitted.status_code})"
        )
    finally:
        client.close()


def test_eko112_unknown_username_d5_master_realm(keycloak_running: Started) -> None:
    """G-01 / S-01: the master-realm destination of the accepted prohibitions, mirroring the
    eko-realm D-5 projection. The D-5 result runs first and on its own, so a session-column
    failure cannot hide it, and vice versa (the two are separate assertions)."""
    composition = keycloak_running.composition
    master = RealmClient(composition, "master")
    try:
        start_ms = int(time.time() * 1000) - 1000
        for marker in fixtures.UNKNOWN_MARKERS:
            refused_master_console_login(composition, marker)
        time.sleep(2.0)  # the store write is part of the request; keep a small settle bound
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        events = master.admin_json(
            breakglass, "GET", "events", realm="master", params={"max": "500"}
        )
        logs = keycloak_logs(keycloak_running)

        # (1) D-5 value class: no unknown marker at any field of any master-realm event, any
        # master admin event, or the container log.
        admin_events = master.admin_json(
            breakglass, "GET", "admin-events", realm="master", params={"max": "500"}
        )
        for marker in fixtures.UNKNOWN_MARKERS:
            candidates = {marker.casefold(), marker.strip().casefold()}
            haystacks = (("master events", events), ("master admin events", admin_events))
            for name, haystack in haystacks:
                hits = [
                    path for event in haystack for path in matching_value_paths(event, candidates)
                ]
                if hits:
                    raise TypedUsernameStop(
                        f"D-5 STOP: unknown typed username matched a {name} field path"
                    )
            if matching_value_paths(logs, candidates, "container-log"):
                raise TypedUsernameStop(
                    "D-5 STOP: unknown typed username matched the Keycloak container log"
                )

        # (2) Field class: the master-realm unknown-account LOGIN_ERROR carriers exist (the
        # store is not empty and the attempts really stored) and none of them carries
        # details.username — the accepted exception names no master realm.
        recent_errors = [
            event
            for event in events
            if event.get("time", 0) >= start_ms and event["type"] == "LOGIN_ERROR"
        ]
        assert len(recent_errors) >= len(fixtures.UNKNOWN_MARKERS), (
            f"the master-realm unknown-account carriers were not stored: window has "
            f"{len(recent_errors)} LOGIN_ERROR events"
        )
        for event in recent_errors:
            details = event.get("details") or {}
            if details.get("username"):
                raise TypedUsernameStop(
                    "D-5 STOP: master-realm LOGIN_ERROR stored details.username "
                    f"(error={event.get('error', '?')})"
                )

        # The contrast that removal is not indiscriminate: the bootstrap's own known-account
        # master verification carrier keeps its username under the base rule.
        assert any(
            event["type"] == "LOGIN_ERROR"
            and (event.get("details") or {}).get("username")
            == fixtures.ACCOUNTS["verification_probe"]
            for event in events
        ), "the known-account master carrier did not retain its username"

        # (3) S-01 field class: no master-realm event keeps a top-level session identifier;
        # the accepted sessionId exception is limited to application-realm events.
        for event in events:
            if event.get("sessionId"):
                raise AssertionError(
                    f"session identifier at non-excepted master:sessionId "
                    f"(event type {event['type']})"
                )
    finally:
        master.close()
