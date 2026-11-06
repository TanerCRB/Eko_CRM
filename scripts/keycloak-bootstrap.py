"""Run inside the existing backend container against the official Keycloak service."""

import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any

BASE_URL = "http://keycloak:8080"
POLICY_FILE = Path("/tmp/eko112-role-mapping-policy.json")
CUSTOM_FACTORY = "org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory"
VERIFICATION_USER = "eko112-verification-probe"
ACCOUNTS = {
    "breakglass_one": "eko112-breakglass-one",
    "breakglass_two": "eko112-breakglass-two",
    "reviewer": "eko112-reviewer",
    "administrator": "eko112-administrator",
}
ADDRESSES = {key: f"{username}@example.org" for key, username in ACCOUNTS.items()}
PASSWORDS = {
    "breakglass_one": "EKO112_BREAKGLASS_ONE_PASSWORD",
    "breakglass_two": "EKO112_BREAKGLASS_TWO_PASSWORD",
    "reviewer": "EKO112_REVIEWER_PASSWORD",
    "administrator": "EKO112_ADMINISTRATOR_PASSWORD",
}
REVIEWER_ROLES = (
    "view-events",
    "view-users",
    "view-realm",
    "view-clients",
    "query-users",
    "query-groups",
    "query-clients",
)


@dataclass
class ApiResponse:
    status_code: int
    body: Any
    headers: Any


class ApiClient:
    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        data: dict[str, str] | None,
        body: Any,
    ) -> ApiResponse:
        request_headers = dict(headers)
        payload = None
        if data is not None:
            payload = urllib.parse.urlencode(data).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            payload = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            BASE_URL + path, data=payload, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                status = response.status
                response_headers = response.headers
        except urllib.error.HTTPError as error:
            raw = error.read()
            status = error.code
            response_headers = error.headers
        parsed = json.loads(raw) if raw else None
        return ApiResponse(status, parsed, response_headers)


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"missing required bootstrap input: {name}")
    return value


def setting(name: str, default: str) -> str:
    return os.environ.get(name, default).strip().lower()


def emit(event: str) -> None:
    print(json.dumps({"event": event}, separators=(",", ":")), flush=True)


def request(
    client: ApiClient,
    method: str,
    path: str,
    *,
    token: str | None = None,
    data: dict[str, str] | None = None,
    body: Any = None,
    expected: tuple[int, ...] = (200,),
) -> ApiResponse:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.request(method, path, headers=headers, data=data, body=body)
    if response.status_code not in expected:
        raise RuntimeError(f"Keycloak {method} {path}: HTTP {response.status_code}")
    return response


def master_token(client: ApiClient, bootstrap: bool) -> str:
    if bootstrap:
        username = required("KC_BOOTSTRAP_ADMIN_USERNAME")
        password = required("KC_BOOTSTRAP_ADMIN_PASSWORD")
    else:
        username = ACCOUNTS["breakglass_one"]
        password = required(PASSWORDS["breakglass_one"])
    response = request(
        client,
        "POST",
        "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        },
    )
    token: str = response.body["access_token"]
    return token


def find_user(client: ApiClient, token: str, realm: str, username: str) -> dict[str, Any] | None:
    response = request(client, "GET", f"/admin/realms/{realm}/users", token=token)
    matches = [item for item in response.body if item.get("username") == username]
    if len(matches) > 1:
        raise RuntimeError("duplicate synthetic bootstrap account")
    return matches[0] if matches else None


def ensure_user(client: ApiClient, token: str, realm: str, key: str) -> dict[str, Any]:
    username = ACCOUNTS[key]
    existing = find_user(client, token, realm, username)
    if existing is not None:
        return existing
    response = request(
        client,
        "POST",
        f"/admin/realms/{realm}/users",
        token=token,
        body={
            "username": username,
            "email": ADDRESSES[key],
            "firstName": "EKO112",
            "lastName": "Synthetic",
            "enabled": True,
        },
        expected=(201,),
    )
    location = response.headers.get("location", "")
    user_id = location.rstrip("/").rsplit("/", 1)[-1]
    if not user_id:
        found = find_user(client, token, realm, username)
        if found is None:
            raise RuntimeError("created synthetic account cannot be read")
        return found
    request(
        client,
        "PUT",
        f"/admin/realms/{realm}/users/{user_id}/reset-password",
        token=token,
        body={"type": "password", "value": required(PASSWORDS[key]), "temporary": False},
        expected=(204,),
    )
    created = find_user(client, token, realm, username)
    if created is None:
        raise RuntimeError("created synthetic account cannot be read")
    return created


def management_client(client: ApiClient, token: str, realm: str, name: str) -> dict[str, Any]:
    response = request(client, "GET", f"/admin/realms/{realm}/clients?clientId={name}", token=token)
    clients = response.body
    if len(clients) != 1:
        raise RuntimeError(f"required management client is unavailable in {realm}")
    client_body: dict[str, Any] = clients[0]
    return client_body


def assign_client_roles(
    client: ApiClient,
    token: str,
    realm: str,
    user_id: str,
    client_name: str,
    role_names: tuple[str, ...],
) -> None:
    management = management_client(client, token, realm, client_name)
    roles = []
    for name in role_names:
        response = request(
            client,
            "GET",
            f"/admin/realms/{realm}/clients/{management['id']}/roles/{name}",
            token=token,
        )
        roles.append(response.body)
    request(
        client,
        "POST",
        f"/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{management['id']}",
        token=token,
        body=roles,
        expected=(204,),
    )


def configure_master(client: ApiClient, bootstrap: bool) -> None:
    token = master_token(client, bootstrap)
    realm = request(client, "GET", "/admin/realms/master", token=token).body
    realm.update(
        {
            "bruteForceProtected": setting("EKO112_MASTER_BRUTE_FORCE", "true") == "true",
            "eventsEnabled": True,
            "adminEventsEnabled": True,
            "adminEventsDetailsEnabled": True,
            "eventsExpiration": 7776000,
            "eventsListeners": [],
        }
    )
    realm.setdefault("attributes", {})["adminEventsExpiration"] = "7776000"
    request(client, "PUT", "/admin/realms/master", token=token, body=realm, expected=(204,))
    for key in ("breakglass_one", "breakglass_two"):
        account = ensure_user(client, token, "master", key)
        role = request(client, "GET", "/admin/realms/master/roles/admin", token=token).body
        request(
            client,
            "POST",
            f"/admin/realms/master/users/{account['id']}/role-mappings/realm",
            token=token,
            body=[role],
            expected=(204,),
        )
    reviewer = ensure_user(client, token, "master", "reviewer")
    assign_client_roles(client, token, "master", reviewer["id"], "master-realm", REVIEWER_ROLES)
    if bootstrap:
        temporary_name = required("KC_BOOTSTRAP_ADMIN_USERNAME")
        temporary = find_user(client, token, "master", temporary_name)
        if temporary is not None and temporary["id"] not in {
            find_user(client, token, "master", ACCOUNTS["breakglass_one"])["id"],
            find_user(client, token, "master", ACCOUNTS["breakglass_two"])["id"],
        }:
            request(
                client,
                "DELETE",
                f"/admin/realms/master/users/{temporary['id']}",
                token=token,
                expected=(204,),
            )
    verification_token = master_token(client, False) if bootstrap else token
    emit("master accounts ready")
    live = request(client, "GET", "/admin/realms/master", token=verification_token).body
    for name, expected in (
        ("eventsEnabled", True),
        ("adminEventsEnabled", True),
        ("eventsExpiration", 7776000),
    ):
        if live.get(name) != expected:
            raise RuntimeError(f"live master setting was not applied: {name}")
    if live.get("attributes", {}).get("adminEventsExpiration") != "7776000":
        raise RuntimeError("live master setting was not applied: adminEventsExpiration")
    if live.get("bruteForceProtected") is not True:
        emit("master bruteForceProtected false")
        raise SystemExit(3)
    emit("master bruteForceProtected true")


def configure_mapping_allow_list(client: ApiClient, token: str) -> None:
    document = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    role_names = [item["name"] for item in document["applicationRoles"]]
    policy_specs = document["adminPermissionsClient"]["authorizationSettings"]["policies"]
    policy_name = next(item["name"] for item in policy_specs if item["type"] == "role")
    realm = request(client, "GET", "/admin/realms/eko", token=token).body
    realm["adminPermissionsEnabled"] = True
    request(client, "PUT", "/admin/realms/eko", token=token, body=realm, expected=(204,))
    permissions_client = management_client(client, token, "eko", "admin-permissions")
    base = f"/admin/realms/eko/clients/{permissions_client['id']}/authz/resource-server"
    application = management_client(client, token, "eko", "eko-backend")
    roles = request(
        client, "GET", f"/admin/realms/eko/clients/{application['id']}/roles", token=token
    ).body
    role_ids = {item["name"]: item["id"] for item in roles}
    administrator_id = role_ids["administrator"]
    existing_policies = request(client, "GET", f"{base}/policy", token=token).body
    existing_policy = next(
        (item for item in existing_policies if item.get("name") == policy_name), None
    )
    policy_body = {
        "name": policy_name,
        "logic": "POSITIVE",
        "roles": [{"id": administrator_id}],
    }
    if existing_policy is None:
        created = request(
            client,
            "POST",
            f"{base}/policy/role",
            token=token,
            body=policy_body,
            expected=(201,),
        )
        policy_id = created.headers.get("location", "").rstrip("/").rsplit("/", 1)[-1]
        if not policy_id and isinstance(created.body, dict):
            policy_id = created.body.get("id", "")
    else:
        policy_id = existing_policy["id"]
        # The role policy can arrive with the realm import (the versioned export carries the
        # allow-list), and Keycloak's update returns the stored representation. Reconcile the
        # imported entry to the live role identifier.
        request(
            client,
            "PUT",
            f"{base}/policy/role/{policy_id}",
            token=token,
            body={"id": policy_id, **policy_body},
            expected=(200, 201, 204),
        )
    if not policy_id:
        raise RuntimeError("application role policy has no identifier")
    existing_permissions = request(client, "GET", f"{base}/permission/scope", token=token).body
    for role_name in role_names:
        permission_name = f"eko112-map-{role_name}"
        permission_body = {
            "name": permission_name,
            "resourceType": "Roles",
            "scopes": ["map-role"],
            "resources": [role_ids[role_name]],
            "policies": [policy_id],
            "decisionStrategy": "UNANIMOUS",
        }
        existing = next(
            (
                item
                for item in existing_permissions
                if item.get("name") == permission_name
            ),
            None,
        )
        if existing is None:
            request(
                client,
                "POST",
                f"{base}/permission/scope",
                token=token,
                body=permission_body,
                expected=(201,),
            )
        else:
            # Reconcile an imported permission to the live role identifier; Keycloak's update
            # on the authorization resource server answers with the stored representation.
            request(
                client,
                "PUT",
                f"{base}/permission/scope/{existing['id']}",
                token=token,
                body={"id": existing["id"], **permission_body},
                expected=(200, 201, 204),
            )

    def live_names(path: str) -> set[str]:
        body = request(client, "GET", f"{base}/{path}", token=token).body
        return {str(item.get("name", "")) for item in body}

    live_policies = live_names("policy")
    live_permissions = live_names("permission/scope")
    if policy_name not in live_policies:
        raise RuntimeError("mapping allow-list role policy is absent after reconciliation")
    for role_name in role_names:
        permission_name = f"eko112-map-{role_name}"
        if permission_name not in live_policies | live_permissions:
            raise RuntimeError(f"map-role permission for {role_name} is absent after reconciliation")


def configure_application(client: ApiClient) -> None:
    token = master_token(client, False)
    if setting("EKO112_APPLICATION_IMPORT", "true") != "true":
        emit("application realm import incomplete")
        raise SystemExit(4)
    emit("application realm import complete")
    application = management_client(client, token, "eko", "eko-backend")
    application["secret"] = required("OIDC_CLIENT_SECRET")
    application["directAccessGrantsEnabled"] = False
    request(
        client,
        "PUT",
        f"/admin/realms/eko/clients/{application['id']}",
        token=token,
        body=application,
        expected=(204,),
    )
    administrator = ensure_user(client, token, "eko", "administrator")
    assign_client_roles(
        client, token, "eko", administrator["id"], "eko-backend", ("administrator",)
    )
    configure_mapping_allow_list(client, token)
    reviewer = find_user(client, token, "master", ACCOUNTS["reviewer"])
    if reviewer is None:
        raise RuntimeError("reviewer account is unavailable")
    assign_client_roles(client, token, "master", reviewer["id"], "eko-realm", REVIEWER_ROLES)
    realm = request(client, "GET", "/admin/realms/eko", token=token).body
    development = setting("EKO112_DEVELOPMENT", "true") == "true"
    realm["resetPasswordAllowed"] = development
    realm["bruteForceProtected"] = setting("EKO112_APPLICATION_BRUTE_FORCE", "true") == "true"
    realm["smtpServer"] = (
        {
            "host": "mailcatcher",
            "port": "1025",
            "from": "eko112-no-reply@example.org",
            "fromDisplayName": "EKO112 synthetic reset",
            "starttls": "false",
            "ssl": "false",
            "auth": "false",
        }
        if development
        else {}
    )
    request(client, "PUT", "/admin/realms/eko", token=token, body=realm, expected=(204,))
    live = request(client, "GET", "/admin/realms/eko", token=token).body
    if live.get("bruteForceProtected") is not True:
        emit("application bruteForceProtected false")
        raise SystemExit(5)
    emit("application bruteForceProtected true")


def raw_get(path: str, headers: dict[str, str]) -> tuple[int, bytes, Any]:
    request = urllib.request.Request(BASE_URL + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers


def raw_post(
    path: str, form: dict[str, str], headers: dict[str, str]
) -> tuple[int, bytes, Any]:
    payload = urllib.parse.urlencode(form).encode()
    request = urllib.request.Request(
        BASE_URL + path,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers


def verification_redirect() -> str:
    host = required("AUTH_ADMIN_HOST")
    port = required("PROXY_ADMIN_PORT")
    return f"https://{host}:{port}/admin/master/console/"


def failed_browser_login(client: ApiClient, token: str) -> None:
    """One master-realm code-flow login failure with a wrong password, as a live event carrier."""
    redirect = verification_redirect()
    query = urllib.parse.urlencode(
        {
            "client_id": "security-admin-console",
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid",
            "state": "eko112-verification",
            "code_challenge": secrets.token_urlsafe(48),
            "code_challenge_method": "S256",
        }
    )
    status, page, headers = raw_get(
        "/realms/master/protocol/openid-connect/auth?" + query, {}
    )
    if status != 200:
        raise RuntimeError(f"verification login page status {status}")
    match = re.search(r'<form[^>]+action="([^"]+)"', page.decode("utf-8", "replace"))
    if match is None:
        raise RuntimeError("verification login form not found")
    action = unescape(match.group(1))
    parsed = urllib.parse.urlparse(action)
    cookies = "; ".join(
        value.split(";", 1)[0] for value in (headers.get_all("set-cookie") or [])
    )
    if not cookies:
        raise RuntimeError("verification login carried no session cookie")
    status, _, _ = raw_post(
        parsed.path + ("?" + parsed.query if parsed.query else ""),
        {"username": VERIFICATION_USER, "password": "synthetic-" + secrets.token_urlsafe(24)},
        {"Cookie": cookies},
    )
    if status not in (200, 401):
        raise RuntimeError(f"verification login failure POST status {status}")


def ensure_verification_user(client: ApiClient, token: str) -> dict[str, Any]:
    existing = find_user(client, token, "master", VERIFICATION_USER)
    if existing is not None:
        return existing
    response = request(
        client,
        "POST",
        "/admin/realms/master/users",
        token=token,
        body={
            "username": VERIFICATION_USER,
            "email": f"{VERIFICATION_USER}@example.org",
            "enabled": True,
        },
        expected=(201,),
    )
    location = response.headers.get("location", "")
    user_id = location.rstrip("/").rsplit("/", 1)[-1]
    created = find_user(client, token, "master", VERIFICATION_USER)
    if created is None and not user_id:
        raise RuntimeError("verification account cannot be read")
    request(
        client,
        "PUT",
        f"/admin/realms/master/users/{created['id'] if created else user_id}/reset-password",
        token=token,
        body={"type": "password", "value": "synthetic-" + secrets.token_urlsafe(24), "temporary": False},
        expected=(204,),
    )  # fmt: skip
    return created if created is not None else {"id": user_id, "username": VERIFICATION_USER}


def verify_filtering(client: ApiClient) -> None:
    """Live pre-listener check: the custom store filters its carrier event in the running server.

    The carrier (a master-realm browser login failure) provably reaches the built-in JPA store
    with a non-excepted details.code_id; only an active custom same-ID override removes it. An
    absent or empty event is a failed verification, never a privacy pass.
    """
    token = master_token(client, bootstrap=False)
    account = ensure_verification_user(client, token)
    start_ms = int(time.time() * 1000) - 60_000
    try:
        failed_browser_login(client, token)
        events = request(
            client, "GET", "/admin/realms/master/events?max=100&type=LOGIN_ERROR", token=token
        ).body  # fmt: skip
        mine = [
            event
            for event in events
            if event.get("time", 0) >= start_ms
            and (event.get("details") or {}).get("username") == VERIFICATION_USER
        ]
        if not mine:
            raise RuntimeError("verification carrier event was not stored")
        recent = [event for event in events if event.get("time", 0) >= start_ms]
        if any("code_id" in (event.get("details") or {}) for event in recent):
            raise RuntimeError("non-excepted code_id reached the live store: built-in JPA path")
    finally:
        request(client, "DELETE", f"/admin/realms/master/users/{account['id']}",
                token=token, expected=(204,))  # fmt: skip


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"master", "application", "verify"}:
        raise RuntimeError("usage: keycloak-bootstrap.py master|application|verify")
    client = ApiClient()
    if sys.argv[1] == "master":
        configure_master(client, setting("EKO112_USE_BOOTSTRAP", "false") == "true")
    elif sys.argv[1] == "verify":
        verify_filtering(client)
        emit("filtering verified")
    else:
        configure_application(client)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        print(f"bootstrap failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from None
