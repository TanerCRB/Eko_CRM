"""EKO-1-12 K-04: reset equivalence and live Keycloak log/event privacy."""

import base64
import copy
import hashlib
import html
import json
import re
import secrets
import time
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any, cast
from urllib.parse import urlparse

import httpx
import pytest

from tests.runtime.conftest import Started
from tests.runtime.keycloak_client import (
    FORM_ACTION,
    RealmClient,
    assert_absent,
    decode_sid,
    keycloak_logs,
    matching_value_paths,
)
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime
REQUIRED_AUTH_EVENT_TYPES = {
    "LOGIN",
    "LOGIN_ERROR",
    "LOGOUT",
    "UPDATE_PASSWORD",
    "UPDATE_PASSWORD_ERROR",
    "RESET_PASSWORD",
    "RESET_PASSWORD_ERROR",
    "SEND_RESET_PASSWORD",
    "REFRESH_TOKEN_ERROR",
    "USER_DISABLED_BY_BRUTE_FORCE",
}
# Two of the ten event names in the accepted criterion are not emitted by Keycloak 26.8.1 in
# the accepted configuration; each was verified against the final image, and the underlying
# security control is still proven by behavior or another stored type (see docs/evidence/
# EKO-1-12/k02-k06-runtime-results.md). Not a widened store exception — the reachable half is
# asserted in full and neither name may ever appear in the store.
#   RESET_PASSWORD: not emitted by any application-reachable flow (reset completion stores
#     UPDATE_PASSWORD; the request stores SEND_RESET_PASSWORD; the error stores
#     RESET_PASSWORD_ERROR) — three producer variants tried.
#   USER_DISABLED_BY_BRUTE_FORCE: not emitted under the accepted wait-based lockout
#     (permanentLockout=false); the brute-force control is proven behaviorally instead — after
#     repeated failures even a correct password is refused (see the coverage brute-force step).
UNREACHABLE_ON_KEYCLOAK_26_8 = frozenset({"RESET_PASSWORD", "USER_DISABLED_BY_BRUTE_FORCE"})
REACHABLE_REQUIRED_EVENT_TYPES = REQUIRED_AUTH_EVENT_TYPES - UNREACHABLE_ON_KEYCLOAK_26_8

REQUIRED_ERROR_EVENTS = {
    "LOGIN_ERROR",
    "UPDATE_PASSWORD_ERROR",
    "RESET_PASSWORD_ERROR",
    "REFRESH_TOKEN_ERROR",
}


def assert_required_authentication_events(events: list[dict[str, Any]]) -> None:
    types = {event["type"] for event in events}
    assert REACHABLE_REQUIRED_EVENT_TYPES <= types, (
        "missing required authentication event types: "
        + ", ".join(sorted(REACHABLE_REQUIRED_EVENT_TYPES - types))
    )
    assert types.isdisjoint(UNREACHABLE_ON_KEYCLOAK_26_8 | {"REFRESH_TOKEN", "CODE_TO_TOKEN"})
    for event in events:
        if event["type"] not in REQUIRED_AUTH_EVENT_TYPES:
            continue
        assert event.get("realmId")
        assert event.get("clientId")
        assert event.get("time", 0) > 0
        assert event.get("ipAddress")
        if event["type"] in REQUIRED_ERROR_EVENTS:
            assert event.get("error")


def session_field_projection(
    value: Any, session_id: str, path: str = ""
) -> list[tuple[str, bool]]:
    if isinstance(value, dict):
        return [
            match
            for key, item in value.items()
            for match in session_field_projection(
                item, session_id, f"{path}.{key}" if path else key
            )
        ]
    if isinstance(value, list):
        return [
            match
            for index, item in enumerate(value)
            for match in session_field_projection(item, session_id, f"{path}[{index}]")
        ]
    if path.rsplit(".", 1)[-1] in {"sessionId", "session_id", "code_id"}:
        return [(path, value == session_id)]
    return []


def assert_session_id_scope(
    events: list[dict[str, Any]], session_id: str, destination: str
) -> None:
    accepted_matches = 0
    duplicate_matches = 0
    for event in events:
        top_level = event.get("sessionId")
        code_id = event.get("details", {}).get("code_id")
        if top_level is not None and destination == "application":
            if (
                event["type"] in REQUIRED_AUTH_EVENT_TYPES
                and isinstance(top_level, str)
                and top_level
            ):
                accepted_matches += 1
            else:
                raise AssertionError(f"session identifier at non-excepted {destination}:sessionId")
        # A master/admin event's own sessionId column is part of Keycloak's event
        # representation; the application's identifier may still only reach these stores
        # through the accepted paths, enforced by the code_id rule and the equality scan.
        if code_id is not None:
            if (
                destination == "application"
                and event["type"] == "LOGIN"
                and isinstance(code_id, str)
                and code_id
                and isinstance(top_level, str)
                and top_level
                and code_id == top_level
            ):
                duplicate_matches += 1
            else:
                raise AssertionError(
                    f"session identifier at non-excepted {destination}:details.code_id"
                )
        for path in matching_value_paths(event, {session_id}):
            allowed_top = destination == "application" and path == "sessionId"
            allowed_duplicate = (
                destination == "application"
                and path == "details.code_id"
                and event["type"] == "LOGIN"
                and code_id == top_level
                and bool(code_id)
            )
            if not allowed_top and not allowed_duplicate:
                raise AssertionError(f"session identifier at non-excepted {destination}:{path}")
    if destination == "application":
        projection = [
            (event["type"], path, matches)
            for event in events
            for path, matches in session_field_projection(event, session_id)
        ]
        assert accepted_matches > 0, f"accepted top-level sessionId contrast is empty: {projection}"
        assert duplicate_matches > 0, "non-empty same-event code_id/sessionId evidence is empty"


def test_k04_duplicate_session_exception_requires_same_nonempty_event_values() -> None:
    value = "synthetic-session-id"
    event = {
        "type": "LOGIN",
        "sessionId": value,
        "details": {"code_id": value},
    }
    assert_session_id_scope([event], value, "application")
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda item: item["details"].update(code_id="different-session-id"),
        lambda item: item.update(sessionId=None),
        lambda item: item.update(sessionId=""),
        lambda item: item.update(sessionId="different-session-id"),
        lambda item: item.pop("sessionId"),
        lambda item: item["details"].update(code_id=""),
        lambda item: item["details"].pop("code_id"),
        lambda item: item.update(type="LOGOUT"),
        lambda item: item["details"].update(session_id=value),
    )
    for mutation in mutations:
        changed = copy.deepcopy(event)
        mutation(changed)
        with pytest.raises(AssertionError):
            assert_session_id_scope([changed], value, "application")
    for destination in ("master", "admin", "off-server", "container-log"):
        with pytest.raises(AssertionError):
            assert_session_id_scope([event], value, destination)
    with pytest.raises(AssertionError):
        assert_absent(value, {"session-id": value}, "Keycloak log")
    with pytest.raises(AssertionError):
        assert_required_authentication_events([event])


class VisiblePageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.suppressed = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.suppressed += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.suppressed:
            self.suppressed -= 1

    def handle_data(self, data: str) -> None:
        if not self.suppressed and data.strip():
            self.parts.append(data.strip())


def visible_text(document: str) -> str:
    parser = VisiblePageText()
    parser.feed(document)
    return " ".join(parser.parts)


def ensure_account(
    client: RealmClient,
    token: str,
    username: str,
    address: str,
    password: str,
    enabled: bool,
    *,
    temporary: bool = False,
) -> dict[str, Any]:
    existing = client.admin_json(
        token, "GET", "users", params={"username": username, "exact": "true"}
    )
    if not existing:
        response = client.admin(
            token,
            "POST",
            "users",
            json_body={
                "username": username,
                "email": address,
                "firstName": "EKO112",
                "lastName": "Synthetic",
                "enabled": enabled,
            },
        )
        assert response.status_code == 201, f"fixture create status {response.status_code}"
        existing = client.admin_json(
            token, "GET", "users", params={"username": username, "exact": "true"}
        )
    assert len(existing) == 1
    account = existing[0]
    account["email"] = address
    account["firstName"] = "EKO112"
    account["lastName"] = "Synthetic"
    account["enabled"] = enabled
    assert client.admin(
        token, "PUT", f"users/{account['id']}", json_body=account
    ).status_code == 204
    response = client.admin(
        token,
        "PUT",
        f"users/{account['id']}/reset-password",
        json_body={"type": "password", "value": password, "temporary": temporary},
    )
    assert response.status_code == 204
    return cast(dict[str, Any], account)


def form_inputs(document: str) -> dict[str, str]:
    """Named inputs with values, excluding passwords and submits, from a Keycloak form."""
    inputs: dict[str, str] = {}
    for match in re.finditer(r"<input\b[^>]*>", document):
        tag = match.group(0)
        name_match = re.search(r'name="([^"]+)"', tag)
        type_match = re.search(r'type="([^"]+)"', tag)
        if name_match is None or (type_match and type_match.group(1) in {"submit", "password"}):
            continue
        value_match = re.search(r'value="([^"]*)"', tag)
        inputs[name_match.group(1)] = html.unescape(value_match.group(1)) if value_match else ""
    return inputs


def submit_form(client: RealmClient, document: str, fields: dict[str, str]) -> httpx.Response:
    match = FORM_ACTION.search(document)
    assert match is not None, "form not found"
    action = html.unescape(match.group(1))
    parsed = urlparse(action)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    return client.request("POST", path, data={**form_inputs(document), **fields})


def login_form_action(document: str) -> str:
    match = FORM_ACTION.search(document)
    assert match is not None, "login form not found"
    parsed = urlparse(html.unescape(match.group(1)))
    return parsed.path + ("?" + parsed.query if parsed.query else "")


def begin_pkce_auth(client: RealmClient) -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    query = httpx.QueryParams(
        {
            "client_id": "eko-backend",
            "redirect_uri": "https://eko112.invalid/callback",
            "response_type": "code",
            "scope": "openid",
            "state": "eko112-coverage",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    login = client.request("GET", f"/realms/{client.realm}/protocol/openid-connect/auth?{query}")
    assert login.status_code == 200, f"auth request status {login.status_code}"
    return verifier, login.text


def reach_password_form(client: RealmClient, start: httpx.Response) -> httpx.Response:
    page = start
    for _ in range(8):
        if 'name="password-confirm"' in page.text:
            return page
        assert page.status_code in (302, 303), f"password-form chain status {page.status_code}"
        location = page.headers.get("location", "")
        assert "callback" not in location, "no required password action was demanded"
        parsed = urlparse(location)
        page = client.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""))
    raise AssertionError("password form never appeared")


def reset_action_link(started: Started, public: RealmClient, address: str) -> str:
    reset_response(public, address)
    listing = [m for m in messages(started) if address in json.dumps(m)]
    assert listing, "the reset request produced no catcher message"
    newest = max(listing, key=lambda m: str(m.get("Created", "")))
    raw = public.composition.compose(
        "exec", "-T", "proxy", "wget", "-qO-", f"http://mailcatcher:8025/api/v1/message/{newest['ID']}"
    ).stdout  # fmt: skip
    # Decode the message JSON so a & in the reset link is not left as the & escape.
    body: dict[str, Any] = json.loads(raw)
    plain = body.get("Text") or body.get("Snippet") or ""
    candidates = re.findall(r"https://\S+login-actions/action-token\S+", plain)
    assert candidates, "no reset link in the catcher message"
    return html.unescape(candidates[-1]).rstrip('\\').rstrip('"').rstrip("'")


def drive_reset_form(public: RealmClient, link: str, password: str, confirm: str) -> httpx.Response:
    parsed = urlparse(link)
    page = public.request("GET", parsed.path + "?" + parsed.query)
    form = reach_password_form(public, page)
    return submit_form(public, form.text, {"password-new": password, "password-confirm": confirm})


def reset_response(client: RealmClient, address: str) -> tuple[int, str, float]:
    started = time.perf_counter()
    page = client.request("GET", f"/realms/{client.realm}/login-actions/reset-credentials")
    assert page.status_code == 200, f"reset page status {page.status_code}"
    match = FORM_ACTION.search(page.text)
    assert match is not None, "reset form not found"
    action = html.unescape(match.group(1))
    parsed = urlparse(action)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    response = client.request("POST", path, data={"username": address})
    elapsed = time.perf_counter() - started
    return response.status_code, visible_text(response.text), elapsed


def messages(started: Started) -> list[dict[str, Any]]:
    result = started.composition.compose(
        "exec", "-T", "proxy", "wget", "-qO-", "http://mailcatcher:8025/api/v1/messages"
    )
    body: dict[str, Any] = json.loads(result.stdout)
    return cast(list[dict[str, Any]], body["messages"])


def assert_refused_login(client: RealmClient, username: str, password: str) -> None:
    probe = RealmClient(client.composition, client.realm, listener=client.listener)
    try:
        with pytest.raises(AssertionError, match="login submission status"):
            probe.browser_token(
                username,
                password,
                client_id="eko-backend",
                client_secret=client.composition.env["OIDC_CLIENT_SECRET"],
            )
    finally:
        probe.close()


def test_k04_every_required_event_type_is_stored(keycloak_running: Started) -> None:
    """Generate every Retention-required event; keep the new values out of store and log."""
    composition = keycloak_running.composition
    admin = RealmClient(composition, "eko")
    public = RealmClient(composition, "eko", listener="auth")
    master = RealmClient(composition, "master")
    temporary_password = secrets.token_urlsafe(24)
    updated_password = secrets.token_urlsafe(24)
    mismatched_confirm = secrets.token_urlsafe(24)
    reset_password = secrets.token_urlsafe(24)
    locked_password = secrets.token_urlsafe(24)
    administrator_token = ""

    def app_admin_token() -> str:
        # A fresh admin-listener client per call: browser_token does a full login, and reusing
        # one client would hit its own SSO session and skip the login page (302) on the second
        # call.
        fresh = RealmClient(composition, "eko")
        try:
            tokens = fresh.browser_token(
                fixtures.ACCOUNTS["administrator"],
                composition.env[fixtures.PASSWORD_VARIABLES["administrator"]],
                client_id="eko-backend",
                client_secret=composition.env["OIDC_CLIENT_SECRET"],
            )
        finally:
            fresh.close()
        token: str = str(tokens["access_token"])
        return token

    def delete_fixture_account(token: str, account_name: str) -> None:
        for item in admin.admin_json(
            token, "GET", "users", params={"username": account_name, "exact": "true"}
        ):
            admin.admin(token, "DELETE", f"users/{item['id']}")

    try:
        administrator_token = app_admin_token()
        ensure_account(
            admin,
            administrator_token,
            fixtures.ACCOUNTS["managed"],
            fixtures.ADDRESSES["managed"],
            temporary_password,
            True,
            temporary=True,
        )

        def stored_events() -> list[dict[str, Any]]:
            breakglass = master.direct_master_token(
                fixtures.ACCOUNTS["breakglass_one"],
                composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
            )
            events: list[dict[str, Any]] = master.admin_json(
                breakglass, "GET", "events", realm="eko", params={"max": "500"}
            )
            return events

        # Required-action update flow: log in with the temporary password (username and
        # password only — the login form's action carries the session, adding its hidden
        # inputs would corrupt it, as browser_token also avoids), reach the update form, and
        # submit a matching new password with the form's hidden inputs. The completion stores
        # UPDATE_PASSWORD. Tokens then come from a normal browser_token login with the new
        # password (after a gap past the realm's 1s quick-login check), which stores LOGIN; the
        # code that survives the required-action redirect is deliberately not exchanged.
        _verifier, login_page = begin_pkce_auth(public)
        submitted = public.request(
            "POST",
            login_form_action(login_page),
            data={"username": fixtures.ACCOUNTS["managed"], "password": temporary_password},
        )
        form_page = reach_password_form(public, submitted)
        posted = submit_form(
            public,
            form_page.text,
            {"password-new": updated_password, "password-confirm": updated_password},
        )
        assert posted.status_code in (200, 302), f"update status {posted.status_code}"
        assert "UPDATE_PASSWORD" in {event["type"] for event in stored_events()}, (
            "password update did not store UPDATE_PASSWORD"
        )
        time.sleep(1.6)
        login_client = RealmClient(composition, "eko", listener="auth")
        try:
            tokens = login_client.browser_token(
                fixtures.ACCOUNTS["managed"],
                updated_password,
                client_id="eko-backend",
                client_secret=composition.env["OIDC_CLIENT_SECRET"],
            )
            refreshed = login_client.refresh(
                "eko-backend", tokens["refresh_token"], composition.env["OIDC_CLIENT_SECRET"]
            )
            login_client.logout(
                "eko-backend", refreshed["refresh_token"], composition.env["OIDC_CLIENT_SECRET"]
            )
        finally:
            login_client.close()
        seen = {event["type"] for event in stored_events()}
        assert "LOGIN" in seen, "browser login did not store LOGIN"
        assert "LOGOUT" in seen, "logout did not store LOGOUT"

        refused = public.request(
            "POST",
            "/realms/eko/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "eko-backend",
                "client_secret": composition.env["OIDC_CLIENT_SECRET"],
                "refresh_token": "eko112-invalid-refresh-token",
            },
        )
        assert refused.status_code == 400, f"invalid refresh status {refused.status_code}"

        link = reset_action_link(keycloak_running, public, fixtures.ADDRESSES["managed"])
        bad_form = drive_reset_form(public, link, reset_password, mismatched_confirm)
        assert bad_form.status_code in (200, 302), f"reset mismatch status {bad_form.status_code}"
        # A password-reset completion runs the update action; the confirm mismatch stores
        # UPDATE_PASSWORD_ERROR here rather than in a second update flow.
        assert "UPDATE_PASSWORD_ERROR" in {event["type"] for event in stored_events()}, (
            "the reset-form confirm mismatch did not store UPDATE_PASSWORD_ERROR"
        )
        link = reset_action_link(keycloak_running, public, fixtures.ADDRESSES["managed"])
        good_form = drive_reset_form(public, link, reset_password, reset_password)
        assert good_form.status_code in (200, 302), f"reset status {good_form.status_code}"
        # RESET_PASSWORD_ERROR: replay the now-consumed action token. Keycloak rejects the used
        # token (HTTP 400) and records the failed reset. The stored event is the assertion, not
        # the HTTP status — the invalid-link page is a deliberate no-detail response.
        consumed = urlparse(link)
        public.request("GET", consumed.path + "?" + consumed.query)
        assert "RESET_PASSWORD_ERROR" in {event["type"] for event in stored_events()}, (
            "replaying a consumed reset token did not store RESET_PASSWORD_ERROR"
        )

        administrator_token = app_admin_token()
        ensure_account(
            admin,
            app_admin_token(),
            fixtures.ACCOUNTS["locked"],
            fixtures.ADDRESSES["locked"],
            locked_password,
            True,
        )
        # Brute-force lockout proven by BEHAVIOR, not by an event: past the realm's
        # failureFactor (30), even the CORRECT password is refused with the same "invalid
        # username or password" page (the accepted wait-based lockout emits no
        # USER_DISABLED_BY_BRUTE_FORCE event; see the note above). The final correct-password
        # refusal is the security assertion.
        for attempt in range(40):
            assert_refused_login(
                public,
                fixtures.ACCOUNTS["locked"],
                f"eko112-wrong-{attempt}-{secrets.token_hex(4)}",
            )
        assert_refused_login(public, fixtures.ACCOUNTS["locked"], locked_password)
        login_errors = [
            event["type"]
            for event in stored_events()
            if event["type"] == "LOGIN_ERROR"
        ]
        assert login_errors, "brute-force lockout produced no LOGIN_ERROR evidence"

        events = stored_events()
        assert_required_authentication_events(events)
        assert "REFRESH_TOKEN" not in {event["type"] for event in events}
        assert "CODE_TO_TOKEN" not in {event["type"] for event in events}
        event_text = json.dumps(events, ensure_ascii=False)
        logs = keycloak_logs(keycloak_running)
        forbidden = {
            "temporary-password": temporary_password,
            "updated-password": updated_password,
            "mismatched-confirm": mismatched_confirm,
            "reset-password": reset_password,
            "locked-password": locked_password,
            "access-token": tokens["access_token"],
            "refresh-token": tokens["refresh_token"],
            "invalid-refresh-token": "eko112-invalid-refresh-token",
        }
        assert_absent(event_text, forbidden, "stored events")
        assert_absent(logs, forbidden, "Keycloak log")
    finally:
        if administrator_token:
            for account_name in (fixtures.ACCOUNTS["managed"], fixtures.ACCOUNTS["locked"]):
                delete_fixture_account(administrator_token, account_name)
        admin.close()
        public.close()
        master.close()


def test_k04_reset_and_log_privacy(keycloak_running: Started) -> None:
    composition = keycloak_running.composition
    app_admin = RealmClient(composition, "eko")
    public = RealmClient(composition, "eko", listener="auth")
    master = RealmClient(composition, "master")
    known_password = secrets.token_urlsafe(32)
    disabled_password = secrets.token_urlsafe(32)
    wrong_password = secrets.token_urlsafe(32)
    try:
        administrator_token = app_admin.browser_token(
            fixtures.ACCOUNTS["administrator"],
            composition.env[fixtures.PASSWORD_VARIABLES["administrator"]],
            client_id="eko-backend",
            client_secret=composition.env["OIDC_CLIENT_SECRET"],
        )["access_token"]
        known = ensure_account(
            app_admin,
            administrator_token,
            fixtures.ACCOUNTS["known"],
            fixtures.ADDRESSES["known"],
            known_password,
            True,
        )
        disabled = ensure_account(
            app_admin,
            administrator_token,
            fixtures.ACCOUNTS["disabled"],
            fixtures.ADDRESSES["disabled"],
            disabled_password,
            False,
        )
        assert known["enabled"] is True and disabled["enabled"] is False
        before = len(messages(keycloak_running))
        known_response = reset_response(public, fixtures.ADDRESSES["known"])
        unknown_response = reset_response(public, fixtures.ADDRESSES["unknown"])
        assert known_response[:2] == unknown_response[:2]
        after_pair = messages(keycloak_running)
        assert len(after_pair) == before + 1
        # The catcher list order is not asserted; select the delivered message by recipient.
        assert any(fixtures.ADDRESSES["known"] in json.dumps(message) for message in after_pair)
        assert fixtures.ADDRESSES["unknown"].lower() not in json.dumps(after_pair).lower()
        second_known = reset_response(public, fixtures.ADDRESSES["known"])
        assert second_known[0] == known_response[0]
        assert len(messages(keycloak_running)) == before + 2
        reset_response(public, fixtures.ADDRESSES["disabled"])
        assert_refused_login(public, fixtures.ACCOUNTS["disabled"], disabled_password)

        tokens = public.browser_token(
            fixtures.ACCOUNTS["known"],
            known_password,
            client_id="eko-backend",
            client_secret=composition.env["OIDC_CLIENT_SECRET"],
        )
        refreshed = public.refresh(
            "eko-backend", tokens["refresh_token"], composition.env["OIDC_CLIENT_SECRET"]
        )
        assert_refused_login(public, fixtures.ACCOUNTS["known"], wrong_password)
        for marker in fixtures.UNKNOWN_MARKERS:
            assert_refused_login(public, marker, wrong_password)
        public.logout(
            "eko-backend", refreshed["refresh_token"], composition.env["OIDC_CLIENT_SECRET"]
        )
        cookie_values = {
            f"cookie-{index}": cookie.value
            for index, cookie in enumerate(public._client.cookies.jar)
        }
        sensitive = {
            "access-token": tokens["access_token"],
            "refresh-token": tokens["refresh_token"],
            "refreshed-access-token": refreshed["access_token"],
            "refreshed-refresh-token": refreshed["refresh_token"],
            "id-token": tokens.get("id_token", ""),
            "authorization-code": tokens["_authorization_code"],
            "known-password": known_password,
            "disabled-password": disabled_password,
            "wrong-password": wrong_password,
            "session-id": decode_sid(tokens["access_token"]),
            **cookie_values,
        }
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        events = master.admin_json(breakglass, "GET", "events", realm="eko")
        event_text = json.dumps(events, ensure_ascii=False)
        logs = keycloak_logs(keycloak_running)
        assert_absent(logs, sensitive, "Keycloak log")
        other_sensitive = {
            label: value for label, value in sensitive.items() if label != "session-id"
        }
        assert_absent(event_text, other_sensitive, "stored events")
        session_id = sensitive["session-id"]
        assert_session_id_scope(events, session_id, "application")
        master_events = master.admin_json(breakglass, "GET", "events", realm="master")
        admin_events = master.admin_json(breakglass, "GET", "admin-events", realm="eko")
        assert_session_id_scope(master_events, session_id, "master")
        assert_session_id_scope(admin_events, session_id, "admin")
        assert_required_authentication_events(events)
        known_errors = [
            event
            for event in events
            if event["type"] == "LOGIN_ERROR"
            and event.get("details", {}).get("username") == fixtures.ACCOUNTS["known"]
        ]
        assert known_errors, "known-user contrast did not retain the username"
        log_level = composition.container_env("keycloak").get("KC_LOG_LEVEL", "info").lower()
        assert log_level not in {"debug", "trace"}
        assert "DEBUG" not in logs and "TRACE" not in logs
    finally:
        app_admin.close()
        public.close()
        master.close()
