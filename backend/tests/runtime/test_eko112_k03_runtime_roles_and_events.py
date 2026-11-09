"""EKO-1-12 K-03: real administrator/reviewer operations and stored events."""

import json
import secrets
from typing import Any, cast

import pytest

from tests.runtime.conftest import Started
from tests.runtime.keycloak_client import RealmClient
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime
EXCLUDED_ROLES = (
    "realm-admin",
    "manage-realm",
    "manage-clients",
    "impersonation",
    "view-events",
    "manage-events",
    "manage-identity-providers",
    "manage-authorization",
    "create-client",
    "view-realm",
    "view-identity-providers",
    "view-authorization",
)
ADMIN_COMPOSITE_TEST_ROLES = (
    "manage-users",
    "view-users",
    "query-users",
    "query-groups",
    "query-clients",
    "view-clients",
)
REVIEWER_ROLE_SET = {
    "view-events",
    "view-users",
    "view-realm",
    "view-clients",
    "query-users",
    "query-groups",
    "query-clients",
}


def user(client: RealmClient, token: str, username: str, realm: str = "eko") -> dict[str, Any]:
    users = client.admin_json(
        token, "GET", "users", params={"username": username, "exact": "true"}, realm=realm
    )
    assert len(users) == 1, f"expected one synthetic account in {realm}"
    return cast(dict[str, Any], users[0])


def client_id(client: RealmClient, token: str, name: str, realm: str = "eko") -> str:
    clients = client.admin_json(
        token, "GET", "clients", params={"clientId": name, "search": "true"}, realm=realm
    )
    assert len(clients) == 1, f"expected one client {name}"
    return str(clients[0]["id"])


def role(
    client: RealmClient, token: str, client_uuid: str, name: str, realm: str = "eko"
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        client.admin_json(token, "GET", f"clients/{client_uuid}/roles/{name}", realm=realm),
    )


def mapped_role_names(
    client: RealmClient, token: str, realm: str, user_id: str, client_uuid: str
) -> set[str]:
    mappings = client.admin_json(
        token, "GET", f"users/{user_id}/role-mappings/clients/{client_uuid}", realm=realm
    )
    return {item["name"] for item in mappings}


def test_k03_administrator_operations_denials_and_stored_admin_events(
    keycloak_running: Started,
) -> None:
    composition = keycloak_running.composition
    app = RealmClient(composition, "eko")
    try:
        administrator_name = fixtures.ACCOUNTS["administrator"]
        token = app.browser_token(
            administrator_name,
            composition.env[fixtures.PASSWORD_VARIABLES["administrator"]],
            client_id="eko-backend",
            client_secret=composition.env["OIDC_CLIENT_SECRET"],
        )["access_token"]
        administrator = user(app, token, administrator_name)
        managed_name = fixtures.ACCOUNTS["managed"]
        password = secrets.token_urlsafe(32)
        created = app.admin(
            token,
            "POST",
            "users",
            json_body={
                "username": managed_name,
                "email": fixtures.ADDRESSES["managed"],
                "firstName": "Synthetic",
                "lastName": "Managed",
                "enabled": True,
            },
        )
        assert created.status_code == 201, f"create status {created.status_code}"
        managed = user(app, token, managed_name)
        managed["firstName"] = "Changed"
        assert (
            app.admin(token, "PUT", f"users/{managed['id']}", json_body=managed).status_code == 204
        )
        for enabled in (False, True):
            managed["enabled"] = enabled
            assert (
                app.admin(token, "PUT", f"users/{managed['id']}", json_body=managed).status_code
                == 204
            )
        reset = app.admin(
            token,
            "PUT",
            f"users/{managed['id']}/reset-password",
            json_body={"type": "password", "value": password, "temporary": True},
        )
        assert reset.status_code == 204, f"password reset status {reset.status_code}"
        master = RealmClient(composition, "master")
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        application_client = client_id(app, token, "eko-backend")
        manager = role(app, token, application_client, "manager")
        rep = role(app, token, application_client, "rep")
        for target, assigned_role in ((administrator["id"], manager), (managed["id"], rep)):
            assigned = app.admin(
                token,
                "POST",
                f"users/{target}/role-mappings/clients/{application_client}",
                json_body=[assigned_role],
            )
            assert assigned.status_code == 204, f"application role status {assigned.status_code}"
            assert assigned_role["name"] in mapped_role_names(
                master, breakglass, "eko", target, application_client
            )
            unassigned = app.admin(
                token,
                "DELETE",
                f"users/{target}/role-mappings/clients/{application_client}",
                json_body=[assigned_role],
            )
            assert unassigned.status_code == 204
            assert assigned_role["name"] not in mapped_role_names(
                master, breakglass, "eko", target, application_client
            )

        assert app.admin(token, "GET", "admin-events").status_code in (401, 403)
        assert app.admin(token, "PUT", "", json_body={"realm": "eko"}).status_code in (401, 403)
        assert app.admin(
            token, "PUT", f"clients/{application_client}", json_body={"id": application_client}
        ).status_code in (401, 403)
        assert app.admin(token, "POST", f"users/{managed['id']}/impersonation").status_code not in (
            200,
            204,
        )
        management = client_id(app, token, "realm-management")
        management_roles = app.admin_json(token, "GET", f"clients/{management}/roles")
        assert set(EXCLUDED_ROLES) <= {item["name"] for item in management_roles}
        assert set(ADMIN_COMPOSITE_TEST_ROLES) <= {item["name"] for item in management_roles}
        for denied_role in management_roles:
            role_name = denied_role["name"]
            assert role_name not in mapped_role_names(
                master, breakglass, "eko", managed["id"], management
            )
            denied = app.admin(
                token,
                "POST",
                f"users/{managed['id']}/role-mappings/clients/{management}",
                json_body=[denied_role],
            )
            assert not 200 <= denied.status_code < 300, f"{role_name}: {denied.status_code}"
            assert role_name not in mapped_role_names(
                master, breakglass, "eko", managed["id"], management
            ), f"{role_name}: mapping persisted"

        deleted = app.admin(token, "DELETE", f"users/{managed['id']}")
        assert deleted.status_code == 204
        try:
            events = master.admin_json(breakglass, "GET", "admin-events", realm="eko")
            managed_events = [
                event for event in events if managed["id"] in event.get("resourcePath", "")
            ]
            assert managed_events
            reset_path = f"users/{managed['id']}/reset-password"
            assert any(
                event["operationType"] == "ACTION" and event["resourcePath"] == reset_path
                for event in managed_events
            )
            for event in managed_events:
                reset_action = (
                    event["operationType"] == "ACTION" and event["resourcePath"] == reset_path
                )
                if not reset_action:
                    assert event.get("representation")
                assert event.get("authDetails", {}).get("userId") == administrator["id"]
                assert event["resourcePath"].startswith(f"users/{managed['id']}")
                assert event.get("time", 0) > 0
                assert password not in json.dumps(event)
        finally:
            master.close()
    finally:
        app.close()


def test_k03_reviewer_reads_required_events_and_mappings_but_cannot_write(
    keycloak_running: Started,
) -> None:
    composition = keycloak_running.composition
    master = RealmClient(composition, "master")
    try:
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        reviewer_name = fixtures.ACCOUNTS["reviewer"]
        reviewer = user(master, breakglass, reviewer_name, realm="master")
        reviewer_token = master.direct_master_token(
            reviewer_name, composition.env[fixtures.PASSWORD_VARIABLES["reviewer"]]
        )
        for management_client in ("master-realm", "eko-realm"):
            management = client_id(master, breakglass, management_client, realm="master")
            mappings = master.admin_json(
                breakglass,
                "GET",
                f"users/{reviewer['id']}/role-mappings/clients/{management}",
                realm="master",
            )
            names = {item["name"] for item in mappings}
            assert names == REVIEWER_ROLE_SET
            assert all(name.startswith(("view-", "query-")) for name in names)
            assert not any(name.startswith("manage-") for name in names)
            assert names.isdisjoint({"realm-admin", "impersonation", "admin"})
        master_users = master.admin_json(breakglass, "GET", "users", realm="master")
        holders = 0
        for account in master_users:
            mappings = master.admin_json(
                breakglass,
                "GET",
                f"users/{account['id']}/role-mappings/realm",
                realm="master",
            )
            holders += any(item["name"] == "admin" for item in mappings)
        assert holders == 2
        assert fixtures.ACCOUNTS["breakglass_one"] in {item["username"] for item in master_users}
        assert not any(
            name.startswith("KC_BOOTSTRAP_ADMIN") for name in composition.container_env("keycloak")
        )

        assert master.admin_json(reviewer_token, "GET", "events", realm="master")
        assert master.admin_json(reviewer_token, "GET", "admin-events", realm="master")
        app_admin_events = master.admin_json(reviewer_token, "GET", "admin-events", realm="eko")
        assert app_admin_events
        administrator = user(master, breakglass, fixtures.ACCOUNTS["administrator"])
        application_client = client_id(master, breakglass, "eko-backend")
        assert master.admin_json(
            breakglass,
            "GET",
            f"users/{administrator['id']}/role-mappings/clients/{application_client}",
            realm="eko",
        ), "bootstrap did not retain the administrator application role"
        assert master.admin_json(
            reviewer_token,
            "GET",
            f"users/{administrator['id']}/role-mappings/clients/{application_client}",
            realm="eko",
        )
        assert master.admin(
            reviewer_token,
            "PUT",
            f"users/{administrator['id']}",
            json_body={"enabled": False},
            realm="eko",
        ).status_code in (401, 403)
        assert master.admin(
            reviewer_token,
            "POST",
            f"users/{administrator['id']}/role-mappings/clients/{application_client}",
            json_body=[role(master, breakglass, application_client, "rep")],
            realm="eko",
        ).status_code in (401, 403)
        for realm in ("master", "eko"):
            original = master.admin_json(breakglass, "GET", "", realm=realm)
            changed = dict(original)
            changed["eventsEnabled"] = False
            try:
                assert master.admin(
                    reviewer_token, "PUT", "", json_body=changed, realm=realm
                ).status_code in (401, 403)
            finally:
                current = master.admin_json(breakglass, "GET", "", realm=realm)
                if current["eventsEnabled"] is not original["eventsEnabled"]:
                    master.admin_json(
                        breakglass, "PUT", "", json_body=original, expected=204, realm=realm
                    )
        master_settings = master.admin_json(breakglass, "GET", "", realm="master")
        assert master_settings["eventsEnabled"] is True
        assert master_settings["adminEventsEnabled"] is True
        assert master_settings["eventsExpiration"] == 90 * 24 * 60 * 60
        assert master_settings["attributes"]["adminEventsExpiration"] == str(90 * 24 * 60 * 60)
    finally:
        master.close()


def test_k03_admin_event_representations_identify_actor_and_exclude_password(
    keycloak_running: Started,
) -> None:
    composition = keycloak_running.composition
    master = RealmClient(composition, "master")
    try:
        token = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        existing = master.admin_json(
            token,
            "GET",
            "users",
            params={"username": fixtures.ACCOUNTS["managed"], "exact": "true"},
            realm="eko",
        )
        if not existing:
            created = master.admin(
                token,
                "POST",
                "users",
                json_body={
                    "username": fixtures.ACCOUNTS["managed"],
                    "email": fixtures.ADDRESSES["managed"],
                    "firstName": "EKO112",
                    "lastName": "Synthetic",
                    "enabled": True,
                },
                realm="eko",
            )
            assert created.status_code == 201
        managed = user(master, token, fixtures.ACCOUNTS["managed"])
        managed["firstName"] = "Changed"
        assert (
            master.admin(
                token, "PUT", f"users/{managed['id']}", json_body=managed, realm="eko"
            ).status_code
            == 204
        )
        assert (
            master.admin(token, "DELETE", f"users/{managed['id']}", realm="eko").status_code == 204
        )
        events = master.admin_json(token, "GET", "admin-events", realm="eko")
        operations = [
            event for event in events if event.get("resourcePath", "").startswith("users")
        ]
        assert operations
        assert any(event["operationType"] == "CREATE" for event in operations)
        assert any(event["operationType"] == "UPDATE" for event in operations)
        assert any(event["operationType"] == "DELETE" for event in operations)
        for event in operations:
            assert event.get("time", 0) > 0
            assert event.get("authDetails", {}).get("userId")
            reset_action = event["operationType"] == "ACTION" and event.get(
                "resourcePath", ""
            ).endswith("/reset-password")
            if not reset_action:
                assert event.get("representation")
            serialized = json.dumps(event)
            assert '"value"' not in serialized or '"type":"password"' not in serialized.replace(
                " ", ""
            )
    finally:
        master.close()


def test_k03_client_secret_absent_from_stored_admin_events(keycloak_running: Started) -> None:
    """U-01 closed by observation: neither store of admin events — the application realm's
    (fed by the realm import and the post-import client PUT) nor master's — may hold the
    OIDC client secret value. The reviewer with `view-events` on both management clients is
    exactly the reader the prohibition names, so the check is the read, not the console."""
    composition = keycloak_running.composition
    master = RealmClient(composition, "master")
    try:
        token = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        secret = composition.env["OIDC_CLIENT_SECRET"]
        assert secret, "the synthetic environment carries no client secret to scan for"
        for realm in ("eko", "master"):
            events = master.admin_json(
                token, "GET", "admin-events", realm=realm, params={"max": "500"}
            )
            assert events, f"no admin events stored in {realm}: the scan would pass on absence"
            assert secret not in json.dumps(events), (
                f"the OIDC client secret reached stored {realm}-realm admin events"
            )
            # The same secret never reaches the authentication-event store either.
            auth_events = master.admin_json(
                token, "GET", "events", realm=realm, params={"max": "500"}
            )
            assert secret not in json.dumps(auth_events), (
                f"the OIDC client secret reached stored {realm}-realm events"
            )
    finally:
        master.close()


def test_k03_application_client_carries_no_offline_access_capability(
    keycloak_running: Started,
) -> None:
    """S-02 closed: the live application client (after import and the post-import PUT) holds
    no `offline_access` scope, so no authentication request through it can mint an offline
    session; the U-02 offline refresh path is unreachable by configuration.

    This is the live half of the guard (the versioned-export half is the exact-set check in
    `tests/static/test_eko112_k01_realm_export.py`). With the scope unassigned there is no
    request path through this client that can obtain an offline token; the request-shape
    handling of an unassigned scope (drop or refuse) is Keycloak's own behavior, observed
    and recorded for the fix round in `docs/evidence/EKO-1-12/offline-scope-removal.md`,
    and it is not a capability the composition grants either way."""
    composition = keycloak_running.composition
    master = RealmClient(composition, "master")
    try:
        token = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        clients = master.admin_json(
            token, "GET", "clients", params={"clientId": "eko-backend"}, realm="eko"
        )
        assert len(clients) == 1
        application = master.admin_json(token, "GET", f"clients/{clients[0]['id']}", realm="eko")
        assigned = set(application.get("defaultClientScopes", [])) | set(
            application.get("optionalClientScopes", [])
        )
        assert "offline_access" not in assigned, (
            "the live application client carries the offline_access scope after import+PUT"
        )
    finally:
        master.close()
