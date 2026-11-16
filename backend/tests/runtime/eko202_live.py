"""EKO-2-02 against running Keycloak (ADR-0003-C7, application half): invented staff accounts,
their client-role mappings and enabled flag through the break-glass administrator, test-owned
rows naming a subject, and the shipped `create_app()` built in this process against the live
realm.

The in-process application is the factory's own product with EKO-2-02's probe injected (gate-1
OQ-3 A); only its back channel is pointed at the composition's public listener, through the
proxy port on 127.0.0.1 with the identity host as SNI and `Host`, as `RealmClient` reaches it.
Its database is a throwaway PostgreSQL migrated by the shipped Alembic. Real time throughout:
the realm's own token lifespan, the application's own clock.

Every account, address and row is invented (ADR-0005 synthetic-data rule); passwords and session
cookies are kept in memory and never printed.
"""

import base64
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.runtime import eko201_login as login_flow
from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import RealmClient
from tests.support import eko112_fixtures as eko112
from tests.support import eko202_probe as probe
from tests.support.pg_instance import Postgres

FIRST_NAME = "EKO202"
LAST_NAME = "Synthetic"
SESSION_COOKIE = "__Host-eko_session"
LOGIN_COOKIE = "__Host-eko_login"
SESSION_KEY = base64.urlsafe_b64encode(b"e" * 32).decode("ascii").rstrip("=")
# Test-owned, never a product revision (impact map section 4): rows naming an account's subject.
CREATE_RECORDS = (
    "CREATE TABLE eko202_owned_record "
    "(id serial PRIMARY KEY, subject text NOT NULL, label text NOT NULL)"
)
DROP_RECORDS = "DROP TABLE IF EXISTS eko202_owned_record"
SELECT_RECORDS = "SELECT id, subject, label FROM eko202_owned_record ORDER BY id"
INSERT_RECORD = "INSERT INTO eko202_owned_record (subject, label) VALUES (%s, %s)"
# psql interpolates `:'name'` as a quoted literal in a script read from stdin, never in `-c`.
INSERT_RECORD_PSQL = (
    "INSERT INTO eko202_owned_record (subject, label) VALUES (:'subject', :'label');\n"
)


# Keycloak administration (break-glass, master realm) -----------------------------------------


@dataclass
class Realm:
    composition: Composition

    def _token(self, master: RealmClient) -> str:
        env = self.composition.env
        return master.direct_master_token(
            eko112.ACCOUNTS["breakglass_one"], env[eko112.PASSWORD_VARIABLES["breakglass_one"]]
        )

    @contextmanager
    def admin(self) -> Iterator[tuple[RealmClient, str]]:
        """A master client and a fresh token: the master token's lifespan is short."""
        master = RealmClient(self.composition, "master")
        try:
            yield master, self._token(master)
        finally:
            master.close()

    def _client_uuid(self, master: RealmClient, token: str) -> str:
        found = master.admin_json(
            token, "GET", "clients", params={"clientId": "eko-backend"}, realm="eko"
        )
        assert len(found) == 1
        return str(found[0]["id"])

    def create_account(self, username: str, password: str, roles: list[str]) -> str:
        """A new enabled account holding `roles` of the application's client; returns its id."""
        with self.admin() as (master, token):
            created = master.admin(
                token,
                "POST",
                "users",
                json_body={
                    "username": username,
                    "email": f"{username}@example.org",
                    "firstName": FIRST_NAME,
                    "lastName": LAST_NAME,
                    "enabled": True,
                    "emailVerified": True,
                },
                realm="eko",
            )
            assert created.status_code == 201, f"account create status {created.status_code}"
            [user] = master.admin_json(
                token, "GET", "users", params={"username": username, "exact": "true"}, realm="eko"
            )
            user_id = str(user["id"])
            master.admin_json(
                token,
                "PUT",
                f"users/{user_id}/reset-password",
                json_body={"type": "password", "value": password, "temporary": False},
                expected=204,
                realm="eko",
            )
        self.change_roles(user_id, "POST", roles)
        return user_id

    def change_roles(self, user_id: str, method: str, roles: list[str]) -> None:
        """`POST` assigns, `DELETE` removes the named client roles."""
        with self.admin() as (master, token):
            client = self._client_uuid(master, token)
            mapped = [
                master.admin_json(token, "GET", f"clients/{client}/roles/{name}", realm="eko")
                for name in roles
            ]
            master.admin_json(
                token,
                method,
                f"users/{user_id}/role-mappings/clients/{client}",
                json_body=mapped,
                expected=204,
                realm="eko",
            )

    def role_names(self, user_id: str) -> set[str]:
        with self.admin() as (master, token):
            client = self._client_uuid(master, token)
            mappings = master.admin_json(
                token, "GET", f"users/{user_id}/role-mappings/clients/{client}", realm="eko"
            )
        return {str(item["name"]) for item in mappings}

    def set_enabled(self, user_id: str, enabled: bool) -> None:
        with self.admin() as (master, token):
            user = master.admin_json(token, "GET", f"users/{user_id}", realm="eko")
            user["enabled"] = enabled
            master.admin_json(
                token, "PUT", f"users/{user_id}", json_body=user, expected=204, realm="eko"
            )


def new_password() -> str:
    return "synthetic-" + secrets.token_urlsafe(24)


def unique(name: str) -> str:
    """A username unique to this run, so a rerun on a kept composition never collides."""
    return f"eko202-{name}-{secrets.token_hex(3)}"


# Test-owned rows -----------------------------------------------------------------------------


def plant_in_composition(composition: Composition, subject: str, label: str) -> None:
    composition.compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "eko", "-X", "-q",
        "-v", "ON_ERROR_STOP=1", "-v", f"subject={subject}", "-v", f"label={label}",
        stdin=INSERT_RECORD_PSQL,
    )  # fmt: skip


# The application built in this process against the live realm --------------------------------


class ThroughProxy(httpx.BaseTransport):
    """Sends every request to the proxy's port on 127.0.0.1, keeping the host as SNI and `Host`."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._inner = httpx.HTTPTransport(verify=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        request.url = request.url.copy_with(host="127.0.0.1", port=self._port)
        request.headers["host"] = host
        request.extensions["sni_hostname"] = host
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


@dataclass
class LiveApp:
    composition: Composition
    pg: Postgres
    app: FastAPI
    recorder: probe.Recorder
    client: TestClient

    def request(self, method: str, path: str, session: str | None) -> httpx.Response:
        headers = {"origin": login_flow.app_origin(self.composition)} if method != "GET" else {}
        cookies = {SESSION_COOKIE: session} if session else {}
        answer: httpx.Response = self.client.request(
            method, path, headers=headers, cookies=cookies, follow_redirects=False
        )
        self.client.cookies.clear()
        return answer

    def status(self, method: str, path: str, session: str) -> int:
        return int(self.request(method, path, session).status_code)

    def subject(self, session: str) -> str:
        view = self.request("GET", "/api/auth/session", session)
        assert view.status_code == 200, view.status_code
        return str(view.json()["subject"])

    def login(self, username: str, password: str) -> str:
        """EKO-2-01's full login: start, Keycloak's form and one-time code, the callback.
        Returns the session cookie's value; fails if the callback set none."""
        response = self.attempt_login(username, password)
        assert response is not None and response.status_code == 303, "callback not completed"
        session = login_flow.set_cookies(response).get(SESSION_COOKIE, "")
        assert session, "the callback set no session cookie"
        return session

    def start(self) -> tuple[str, str]:
        started = self.client.get("/api/auth/login", follow_redirects=False)
        self.client.cookies.clear()
        assert started.status_code == 303, started.status_code
        location = urlsplit(started.headers["location"])
        assert location.path == "/realms/eko/protocol/openid-connect/auth"
        login_cookie = login_flow.set_cookies(started)[LOGIN_COOKIE]
        return login_cookie, f"{location.path}?{location.query}"

    def at_keycloak(self, keycloak_path: str, username: str, password: str) -> httpx.Response:
        browser = RealmClient(self.composition, "eko", listener="auth")
        try:
            start = login_flow.LoginStart("", keycloak_path)
            return login_flow.at_keycloak(browser, start, username, password)
        finally:
            browser.close()

    def callback(self, login_cookie: str, redirect: httpx.Response) -> httpx.Response:
        location = urlsplit(redirect.headers["location"])
        answer: httpx.Response = self.client.get(
            f"{location.path}?{location.query}",
            cookies={LOGIN_COOKIE: login_cookie},
            follow_redirects=False,
        )
        self.client.cookies.clear()
        return answer

    def attempt_login(self, username: str, password: str) -> httpx.Response | None:
        """The callback's response, or None when Keycloak ended the flow without a callback."""
        login_cookie, keycloak_path = self.start()
        redirect = self.at_keycloak(keycloak_path, username, password)
        if not login_flow.is_callback_redirect(self.composition, redirect):
            return None
        return self.callback(login_cookie, redirect)

    def session_count(self) -> int:
        return int(self.pg.rows("SELECT count(*) FROM app_session")[0][0])


@contextmanager
def live_app(composition: Composition, pg: Postgres) -> Iterator[LiveApp]:
    from app.main import create_app

    env = composition.env
    settings = {
        **pg.app_env(),
        "APP_ORIGIN": login_flow.app_origin(composition),
        "APP_OIDC_ISSUER": login_flow.issuer(composition),
        "APP_OIDC_CLIENT_SECRET": env["OIDC_CLIENT_SECRET"],
        "APP_SESSION_ENCRYPTION_KEY": SESSION_KEY,
    }
    with pytest.MonkeyPatch.context() as scoped:
        for name, value in settings.items():
            scoped.setenv(name, value)
        scoped.delenv("APP_OIDC_INTERNAL_URL", raising=False)
        app = create_app()
    recorder = probe.install_probe(app)
    channel = httpx.Client(
        transport=ThroughProxy(int(env["PROXY_HTTPS_PORT"])),
        timeout=httpx.Timeout(5.0),
        follow_redirects=False,
    )
    app.state.auth.oidc._http = channel
    try:
        with TestClient(app, base_url=login_flow.app_origin(composition)) as client:
            yield LiveApp(composition, pg, app, recorder, client)
    finally:
        channel.close()


def wait_until(deadline: float, interval: float) -> Iterator[float]:
    """Monotonic instants, one per `interval`, until `deadline`."""
    while (now := time.monotonic()) < deadline:
        yield now
        time.sleep(max(0.0, interval - (time.monotonic() - now)))
