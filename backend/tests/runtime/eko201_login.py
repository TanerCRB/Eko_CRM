"""EKO-2-01: a staff login through the composition's own backend and real callback, against the
running Keycloak behind the public listener. Cookies are kept by the caller, never printed.

The browser is played by two parties: requests to `<app-host>` go through the proxy's
application listener with cookies passed explicitly, and requests to `<auth-host>` go through a
`RealmClient` on the public listener, which keeps Keycloak's own cookies (the SSO cookie
included) in its jar exactly as one browser would.
"""

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.settings import without_default_port
from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import RealmClient, form_path, second_factor
from tests.support import eko201_keycloak as accounts

SESSION_COOKIE = "__Host-eko_session"
LOGIN_COOKIE = "__Host-eko_login"


def app_origin(composition: Composition) -> str:
    env = composition.env
    # As the backend uses it (F-1 A): a default port dropped.
    return without_default_port(f"https://{env['APP_HOST']}:{env['PROXY_HTTPS_PORT']}")


def issuer(composition: Composition) -> str:
    env = composition.env
    return without_default_port(f"https://{env['AUTH_HOST']}:{env['PROXY_HTTPS_PORT']}/realms/eko")


def app_request(
    composition: Composition,
    method: str,
    path: str,
    cookies: dict[str, str] | None = None,
    origin: str | None = None,
) -> httpx.Response:
    headers: dict[str, str] = {}
    if cookies:
        headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
    if origin is not None:
        headers["Origin"] = origin
    return composition.through_proxy("app", path, method=method, headers=headers)


def set_cookies(response: httpx.Response) -> dict[str, str]:
    """Cookies the response sets with a value (cleared ones are left out)."""
    found: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        first = header.split(";", 1)[0]
        name, _, value = first.partition("=")
        attributes = header.lower()
        if value and "max-age=0" not in attributes:
            found[name.strip()] = value.strip().strip('"')
    return found


@dataclass
class LoginStart:
    login_cookie: str
    keycloak_path: str


def start_login(composition: Composition, return_to: str = "/") -> LoginStart:
    started = app_request(composition, "GET", f"/api/auth/login?return_to={quote(return_to)}")
    assert started.status_code == 303, f"login start status {started.status_code}"
    location = urlparse(started.headers["location"])
    assert (
        f"https://{location.netloc}{location.path}"
        == f"{issuer(composition)}/protocol/openid-connect/auth"
    ), location.netloc
    assert location.path == "/realms/eko/protocol/openid-connect/auth"
    cookie = set_cookies(started).get(LOGIN_COOKIE, "")
    assert cookie, "no login-transaction cookie"
    return LoginStart(cookie, f"{location.path}?{location.query}")


def at_keycloak(
    keycloak: RealmClient, start: LoginStart, username: str, password: str
) -> httpx.Response:
    """The response that ends the identity-server part: a redirect to the callback, or the
    page Keycloak stopped on. A redirect without the form means a silent SSO login."""
    page = keycloak.request("GET", start.keycloak_path)
    if page.status_code in (302, 303):
        return page
    assert page.status_code == 200, f"login page status {page.status_code}"
    submitted = keycloak.request(
        "POST", form_path(page.text), data={"username": username, "password": password}
    )
    return second_factor(keycloak, username, submitted)


def is_callback_redirect(composition: Composition, response: httpx.Response) -> bool:
    if response.status_code not in (302, 303):
        return False
    location = urlparse(response.headers.get("location", ""))
    return (
        f"{location.scheme}://{location.netloc}" == app_origin(composition)
        and location.path == "/api/auth/callback"
        and "code=" in location.query
    )


def finish_login(
    composition: Composition, start: LoginStart, redirect: httpx.Response
) -> httpx.Response:
    assert is_callback_redirect(composition, redirect), (
        f"identity server ended with status {redirect.status_code}, not the callback"
    )
    location = urlparse(redirect.headers["location"])
    return app_request(
        composition,
        "GET",
        f"{location.path}?{location.query}",
        cookies={LOGIN_COOKIE: start.login_cookie},
    )


def login(composition: Composition, keycloak: RealmClient, username: str, password: str) -> str:
    """A complete login through the backend; returns the new session cookie's value."""
    start = start_login(composition)
    callback = finish_login(composition, start, at_keycloak(keycloak, start, username, password))
    assert callback.status_code == 303, f"callback status {callback.status_code}"
    session = set_cookies(callback).get(SESSION_COOKIE, "")
    assert session, "the callback set no session cookie"
    return session


def session_view(composition: Composition, session: str) -> httpx.Response:
    return app_request(composition, "GET", "/api/auth/session", cookies={SESSION_COOKIE: session})


def logout(composition: Composition, session: str) -> httpx.Response:
    return app_request(
        composition,
        "POST",
        "/api/auth/logout",
        cookies={SESSION_COOKIE: session},
        origin=app_origin(composition),
    )


def session_count(composition: Composition) -> int:
    return int(composition.sql("SELECT count(*) FROM app_session")[0][0])


def stored_token_claims(composition: Composition) -> list[dict[str, dict[str, Any]]]:
    """Every stored session's three tokens, decrypted the backend's own way and decoded.

    `Sealer(settings.session_key()).open(row.tokens, row.session_hash)` then
    `TokenSet.from_bytes` (developer-backend hand-back); the key is the composition's own
    synthetic SESSION_ENCRYPTION_KEY. Payloads are decoded without verification: the backend
    verified them when it stored them, and this read only inspects claim names.
    """
    from app.auth.crypto import Sealer
    from app.auth.oidc import TokenSet

    raw_key = composition.env["SESSION_ENCRYPTION_KEY"]
    key = base64.urlsafe_b64decode(raw_key + "=" * (-len(raw_key) % 4))
    sealer = Sealer(key)
    rows = composition.sql(
        "SELECT session_hash, encode(tokens, 'hex') FROM app_session ORDER BY id"
    )
    sessions = []
    for session_hash, sealed in rows:
        tokens = TokenSet.from_bytes(sealer.open(bytes.fromhex(sealed), session_hash))
        sessions.append(
            {
                kind: payload(token)
                for kind, token in (
                    ("access", tokens.access),
                    ("refresh", tokens.refresh),
                    ("id", tokens.id),
                )
                if token
            }
        )
    return sessions


def stored_token_texts(composition: Composition) -> str:
    """Every stored session's decrypted token set as text, for the secret scan."""
    from app.auth.crypto import Sealer

    raw_key = composition.env["SESSION_ENCRYPTION_KEY"]
    key = base64.urlsafe_b64decode(raw_key + "=" * (-len(raw_key) % 4))
    sealer = Sealer(key)
    rows = composition.sql(
        "SELECT session_hash, encode(tokens, 'hex') FROM app_session ORDER BY id"
    )
    parts = []
    for session_hash, sealed in rows:
        plain = sealer.open(bytes.fromhex(sealed), session_hash).decode("utf-8")
        parts.append(plain)
        for token in json.loads(plain).values():
            if isinstance(token, str):
                parts.extend(json.dumps(item) for item in [payload(token)] if item)
    return "\n".join(parts)


def payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    decoded: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
    )
    return decoded


def ensure_staff_account(
    realm_admin: RealmClient, token: str, key: str, password: str, *, temporary: bool = False
) -> str:
    """Create (or reset) one invented staff account in the application realm; returns its id."""
    username = accounts.ACCOUNTS[key]
    found = realm_admin.admin_json(
        token, "GET", "users", params={"username": username, "exact": "true"}, realm="eko"
    )
    if not found:
        created = realm_admin.admin(
            token,
            "POST",
            "users",
            json_body={
                "username": username,
                "email": accounts.ADDRESSES[key],
                "firstName": accounts.FIRST_NAME,
                "lastName": accounts.LAST_NAME,
                "enabled": True,
                "emailVerified": True,
            },
            realm="eko",
        )
        assert created.status_code == 201, f"account create status {created.status_code}"
        found = realm_admin.admin_json(
            token, "GET", "users", params={"username": username, "exact": "true"}, realm="eko"
        )
    assert len(found) == 1
    user_id = str(found[0]["id"])
    reset = realm_admin.admin(
        token,
        "PUT",
        f"users/{user_id}/reset-password",
        json_body={"type": "password", "value": password, "temporary": temporary},
        realm="eko",
    )
    assert reset.status_code == 204, f"password set status {reset.status_code}"
    return user_id
