"""EKO-2-01 K-06 / ADR-0003-C32 against running Keycloak: the OTP credential's life and where
its secret never goes.

One invented staff account enrols an OTP credential at its first real login through the
backend; a privileged read confirms it; the next login asks only for a code (and refuses a
wrong one). An account holding only `administrator` removes the credential: a stored admin
event names the acting account, the affected account and the time, and the next login demands
a new enrolment, whose secret differs. Throughout, the versioned and the live realm export,
every stored application- and master-realm event and admin event, the credential
representation, the Keycloak and backend logs and the application database (its decrypted
tokens included) hold neither secret, in its stored or its displayed form, nor any code typed.
Each source is proven read: planting a secret or a code into a copy of it fails the scan for
that source, and the application-realm store that holds no MFA event does hold the account's
LOGIN events (G-E A).
"""

import json
import secrets
import time
from typing import Any

import httpx
import pytest

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Composition, Started
from tests.runtime.keycloak_client import (
    OTP_SECRETS,
    OTP_TYPED_CODES,
    RealmClient,
    form_path,
    hidden_inputs,
    is_code_page,
    is_enrolment_page,
    keycloak_logs,
    second_factor,
)
from tests.support import eko112_fixtures as eko112
from tests.support import eko201_keycloak as accounts
from tests.support import totp
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime


def until_page(keycloak: RealmClient, response: httpx.Response) -> httpx.Response:
    """Follow Keycloak's in-flow redirects to the page it stops on, answering nothing."""
    for _ in range(6):
        if response.status_code not in (302, 303):
            return response
        location = httpx.URL(response.headers["location"])
        if "/login-actions/" not in location.path:
            return response
        response = keycloak.request("GET", location.raw_path.decode())
    return response


def password_step(
    composition: Composition, username: str, password: str
) -> tuple[RealmClient, app.LoginStart, httpx.Response]:
    keycloak = RealmClient(composition, "eko", listener="auth")
    start = app.start_login(composition)
    page = keycloak.request("GET", start.keycloak_path)
    assert page.status_code == 200, page.status_code
    submitted = keycloak.request(
        "POST", form_path(page.text), data={"username": username, "password": password}
    )
    return keycloak, start, until_page(keycloak, submitted)


def wrong_code(raw_secret: str) -> str:
    now = totp.time_step()
    valid = {totp.totp(totp.keycloak_key(raw_secret), step) for step in range(now - 2, now + 3)}
    while True:
        candidate = f"{secrets.randbelow(10**6):06d}"
        if candidate not in valid:
            return candidate


def admin_get(master: RealmClient, token: str, path: str, realm: str) -> Any:
    return master.admin_json(token, "GET", path, realm=realm, params={"max": "5000"})


def test_k06_otp_enrolment_removal_reenrolment_and_secret_scan(
    keycloak_running: Started,
) -> None:
    composition = keycloak_running.composition
    env = composition.env
    master = RealmClient(composition, "master")
    administrator_client = RealmClient(composition, "eko")
    opened: list[RealmClient] = [master, administrator_client]
    sessions: list[str] = []
    username = accounts.ACCOUNTS["mfa"]
    key = (composition.project, "eko", username)
    refused_codes: list[str] = []
    started_ms = int(time.time() * 1000) - 5_000
    try:
        breakglass = master.direct_master_token(
            eko112.ACCOUNTS["breakglass_one"], env[eko112.PASSWORD_VARIABLES["breakglass_one"]]
        )
        password = "synthetic-" + secrets.token_urlsafe(24)
        user_id = app.ensure_staff_account(master, breakglass, "mfa", password)
        assert not [
            item
            for item in master.admin_json(
                breakglass, "GET", f"users/{user_id}/credentials", realm="eko"
            )
            if item["type"] == "otp"
        ], "premise: the account starts without an OTP credential"

        # 1. First login: the realm demands enrolment.
        keycloak, start, page = password_step(composition, username, password)
        opened.append(keycloak)
        assert page.status_code == 200 and is_enrolment_page(page.text), "no enrolment demanded"
        done = second_factor(keycloak, username, page)
        callback = app.finish_login(composition, start, done)
        sessions.append(app.set_cookies(callback)[app.SESSION_COOKIE])
        first_secret = OTP_SECRETS[key]
        otp = [
            item
            for item in master.admin_json(
                breakglass, "GET", f"users/{user_id}/credentials", realm="eko"
            )
            if item["type"] == "otp"
        ]
        assert len(otp) == 1, "the privileged read finds no OTP credential"

        # 2. Contrast: without a removal, the next login asks only for a code, and refuses a
        # wrong one.
        keycloak, start, page = password_step(composition, username, password)
        opened.append(keycloak)
        assert page.status_code == 200 and is_code_page(page.text)
        assert not is_enrolment_page(page.text)
        refused_codes.append(wrong_code(first_secret))
        refused = keycloak.request(
            "POST",
            form_path(page.text),
            data={**hidden_inputs(page.text), "otp": refused_codes[-1]},
        )
        assert refused.status_code == 200 and is_code_page(refused.text), "wrong code accepted"
        done = second_factor(keycloak, username, refused)
        sessions.append(
            app.set_cookies(app.finish_login(composition, start, done))[app.SESSION_COOKIE]
        )

        # 3. An account holding only `administrator` removes the credential.
        administrator = master.admin_json(
            breakglass,
            "GET",
            "users",
            params={"username": eko112.ACCOUNTS["administrator"], "exact": "true"},
            realm="eko",
        )[0]
        mappings = master.admin_json(
            breakglass, "GET", f"users/{administrator['id']}/role-mappings", realm="eko"
        )
        assert {role["name"] for role in mappings.get("realmMappings", [])} == {"default-roles-eko"}
        assert {
            client: sorted(role["name"] for role in body["mappings"])
            for client, body in mappings.get("clientMappings", {}).items()
        } == {"eko-backend": ["administrator"]}
        administrator_token = administrator_client.browser_token(
            eko112.ACCOUNTS["administrator"],
            env[eko112.PASSWORD_VARIABLES["administrator"]],
            client_id="eko-backend",
            client_secret=env["OIDC_CLIENT_SECRET"],
        )["access_token"]
        removed = administrator_client.admin(
            administrator_token, "DELETE", f"users/{user_id}/credentials/{otp[0]['id']}"
        )
        assert removed.status_code == 204, removed.status_code
        admin_events = admin_get(master, breakglass, "admin-events", "eko")
        removal = [
            event
            for event in admin_events
            if event.get("resourcePath") == f"users/{user_id}/credentials/{otp[0]['id']}"
        ]
        assert len(removal) == 1, "the removal is not one stored admin event"
        assert removal[0]["authDetails"]["userId"] == administrator["id"]
        assert removal[0]["time"] >= started_ms
        assert removal[0]["operationType"] in {"DELETE", "ACTION"}

        # 4. The next login demands a new enrolment, with a new secret.
        keycloak, start, page = password_step(composition, username, password)
        opened.append(keycloak)
        assert page.status_code == 200 and is_enrolment_page(page.text), "re-enrolment not forced"
        done = second_factor(keycloak, username, page)
        sessions.append(
            app.set_cookies(app.finish_login(composition, start, done))[app.SESSION_COOKIE]
        )
        second_secret = OTP_SECRETS[key]
        assert second_secret != first_secret

        # 5. The scan.
        material = accounts.OtpMaterial(
            secrets=[first_secret, second_secret],
            codes=[*OTP_TYPED_CODES[key], *refused_codes],
        )
        assert len(material.codes) >= 4
        live_export = master.request(
            "POST",
            "/admin/realms/eko/partial-export?exportClients=true&exportGroupsAndRoles=true",
            token=breakglass,
        )
        assert live_export.status_code == 200, live_export.status_code
        application_events = admin_get(master, breakglass, "events", "eko")
        dump = composition.compose(
            "exec", "-T", "postgres", "pg_dump", "-U", "postgres", "-d", "eko", "--data-only"
        ).stdout
        backend_logs = composition.compose("logs", "--no-color", "backend", check=False)
        sources = {
            "versioned realm export": (REPO_ROOT / "identity" / "eko-realm.json").read_text(
                encoding="utf-8"
            ),
            "live realm export": live_export.text,
            "application-realm events": json.dumps(application_events),
            "application-realm admin events": json.dumps(
                admin_get(master, breakglass, "admin-events", "eko")
            ),
            "master-realm events": json.dumps(admin_get(master, breakglass, "events", "master")),
            "master-realm admin events": json.dumps(
                admin_get(master, breakglass, "admin-events", "master")
            ),
            "credential representation": json.dumps(
                master.admin_json(breakglass, "GET", f"users/{user_id}/credentials", realm="eko")
            ),
            "Keycloak log": keycloak_logs(keycloak_running),
            "backend log": backend_logs.stdout + backend_logs.stderr,
            "application database": dump + "\n" + app.stored_token_texts(composition),
        }
        assert all(sources.values()), [name for name, text in sources.items() if not text]
        assert accounts.scan_findings(sources, material) == []

        # The stores are read: the account's logins are there, MFA events are not (G-E A).
        mine = [event for event in application_events if event.get("userId") == user_id]
        assert len([event for event in mine if event["type"] == "LOGIN"]) >= 3
        stored_types = {event["type"] for event in application_events}
        assert stored_types.isdisjoint(accounts.MFA_EVENT_TYPES), stored_types
        live_realm = master.admin_json(breakglass, "GET", "", realm="eko")
        export = json.loads(sources["versioned realm export"])
        assert sorted(live_realm["enabledEventTypes"]) == sorted(export["enabledEventTypes"])

        # Planted contrasts: the secret (stored and displayed forms) and a typed code, copied
        # into each source in turn, fail the scan for exactly that source.
        for name in sources:
            for planted_value, label in (
                (first_secret, "secret 0 (raw)"),
                (
                    accounts.secret_forms(second_secret)["base32-grouped"],
                    "secret 1 (base32-grouped)",
                ),
                (material.codes[0], "typed code 0"),
            ):
                planted = {**sources, name: sources[name] + f"\n {planted_value} \n"}
                found = accounts.scan_findings(planted, material)
                assert f"{name}: {label}" in found, (name, label)
                assert all(item.startswith(f"{name}:") for item in found)
    finally:
        for session in sessions:
            app.logout(composition, session)
        for client in opened:
            client.close()
