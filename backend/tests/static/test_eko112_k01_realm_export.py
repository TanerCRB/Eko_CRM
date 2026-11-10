"""EKO-1-12 K-01: the versioned application realm is the configuration under test."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tests.support.repo import REPO_ROOT

EXPORT = REPO_ROOT / "identity" / "eko-realm.json"
STORED_LOGIN_TYPES = {
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
ADMIN_COMPOSITE = {
    "manage-users",
    "view-users",
    "query-users",
    "query-groups",
    "query-clients",
    "view-clients",
}


@pytest.fixture
def realm() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(EXPORT.read_text(encoding="utf-8"))
    return loaded


def client(realm: dict[str, Any], client_id: str) -> dict[str, Any]:
    return next(item for item in realm["clients"] if item["clientId"] == client_id)


def test_k01_registration_broker_and_brute_force_configuration(realm: dict[str, Any]) -> None:
    assert realm["registrationAllowed"] is False
    assert realm["bruteForceProtected"] is True
    assert realm["identityProviders"] == []


def test_k01_every_client_has_direct_access_disabled(realm: dict[str, Any]) -> None:
    assert realm["clients"]
    assert all(item.get("directAccessGrantsEnabled") is False for item in realm["clients"])


def test_k01_application_client_is_confidential_with_pkce_and_rotating_refresh_tokens(
    realm: dict[str, Any],
) -> None:
    application = client(realm, "eko-backend")
    assert application["publicClient"] is False
    assert application["attributes"]["pkce.code.challenge.method"] == "S256"
    assert realm["revokeRefreshToken"] is True
    assert realm["refreshTokenMaxReuse"] == 0


def test_k01_application_token_contains_no_email_or_username_scope_or_mapper(
    realm: dict[str, Any],
) -> None:
    application = client(realm, "eko-backend")
    assigned = set(application.get("defaultClientScopes", [])) | set(
        application.get("optionalClientScopes", [])
    )
    assert assigned.isdisjoint({"email", "profile", "offline_access"})
    # S-02: the scope set is checked exactly, so an unapproved capability cannot ride in
    # through a list the earlier disjoint checks would not name. No accepted decision
    # (ADR-0003/0005, Issue #53 K-01) assigns the application client an offline session.
    assert application.get("optionalClientScopes", []) == [], (
        "the application client carries optional scopes no accepted decision names"
    )
    emitted = {
        mapper.get("config", {}).get("claim.name")
        for mapper in application.get("protocolMappers", [])
    }
    assert emitted.isdisjoint({"email", "preferred_username"})


def test_k01_offline_access_on_the_application_client_fails_the_exact_set_guard(
    realm: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(realm)
    application = client(mutated, "eko-backend")
    application["optionalClientScopes"] = ["offline_access"]
    with pytest.raises(AssertionError):
        test_k01_application_token_contains_no_email_or_username_scope_or_mapper(mutated)


def test_k01_names_are_admin_editable_only_and_account_console_roles_are_not_defaults(
    realm: dict[str, Any],
) -> None:
    profile = json.loads(realm["attributes"]["userProfile"])
    attributes = {item["name"]: item for item in profile["attributes"]}
    for name in ("firstName", "lastName"):
        assert attributes[name]["permissions"]["edit"] == ["admin"]
    default_role = next(
        item for item in realm["roles"]["realm"] if item["name"] == realm["defaultRole"]["name"]
    )
    account_defaults = set(default_role.get("composites", {}).get("client", {}).get("account", []))
    assert account_defaults.isdisjoint({"manage-account", "view-profile"})


def test_k01_administrator_composite_is_exact_and_no_other_role_or_group_escalates(
    realm: dict[str, Any],
) -> None:
    administrator = next(
        item for item in realm["roles"]["client"]["eko-backend"] if item["name"] == "administrator"
    )
    assert set(administrator["composites"]["client"]["realm-management"]) == ADMIN_COMPOSITE
    for client_name, roles in realm["roles"]["client"].items():
        for role in roles:
            if client_name == "eko-backend" and role["name"] == "administrator":
                continue
            assert "realm-management" not in role.get("composites", {}).get("client", {})
    for role in realm["roles"]["realm"]:
        assert "realm-management" not in role.get("composites", {}).get("client", {})
    for group in realm.get("groups", []):
        assert "realm-management" not in group.get("clientRoles", {})


def test_k01_fine_grained_mapping_allow_list_is_exactly_three_application_roles(
    realm: dict[str, Any],
) -> None:
    assert realm["adminPermissionsEnabled"] is True
    document = json.loads(
        (REPO_ROOT / "identity" / "eko-role-mapping-policy.json").read_text(encoding="utf-8")
    )
    policies = document["adminPermissionsClient"]["authorizationSettings"]["policies"]
    role_policy = next(
        item for item in policies if item["name"] == "eko112-application-administrator"
    )
    assert role_policy["type"] == "role"
    application_roles = {item["name"]: item["id"] for item in document["applicationRoles"]}
    assert set(application_roles) == {"rep", "manager", "administrator"}
    assert json.loads(role_policy["config"]["roles"]) == [
        {"id": application_roles["administrator"], "required": False}
    ]
    permissions = [
        item
        for item in policies
        if item.get("resourceType") == "Roles"
        and [scope["name"] for scope in item.get("scopesData", [])] == ["map-role"]
    ]
    assert {item["name"] for item in permissions} == {
        "eko112-map-rep",
        "eko112-map-manager",
        "eko112-map-administrator",
    }
    for permission in permissions:
        role_name = permission["name"].removeprefix("eko112-map-")
        assert permission["type"] == "scope"
        assert permission["decisionStrategy"] == "UNANIMOUS"
        assert permission["resourcesData"] == [
            {"name": application_roles[role_name], "displayName": role_name}
        ]
        assert permission["policies"] == [role_policy["id"]]


def test_k01_event_configuration_and_exact_retention(realm: dict[str, Any]) -> None:
    assert realm["adminEventsEnabled"] is True
    assert realm["adminEventsDetailsEnabled"] is True
    assert realm["attributes"]["adminEventsExpiration"] == str(90 * 24 * 60 * 60)
    assert realm["eventsEnabled"] is True
    assert realm["eventsExpiration"] == 30 * 24 * 60 * 60
    assert set(realm["enabledEventTypes"]) == STORED_LOGIN_TYPES
    assert "REFRESH_TOKEN" not in realm["enabledEventTypes"]
    assert "CODE_TO_TOKEN" not in realm["enabledEventTypes"]


def test_k01_access_token_lifespan_leaves_a_positive_remainder(realm: dict[str, Any]) -> None:
    assert 0 < realm["accessTokenLifespan"] < 300


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda realm: realm.update(registrationAllowed=True), id="registration"),
        pytest.param(lambda realm: realm.update(bruteForceProtected=False), id="brute-force"),
        pytest.param(lambda realm: realm.update(accessTokenLifespan=300), id="token-budget"),
        pytest.param(
            lambda realm: realm.update(adminEventsDetailsEnabled=False), id="event-detail"
        ),
        pytest.param(lambda realm: realm.update(eventsExpiration=0), id="login-retention"),
        pytest.param(
            lambda realm: realm["attributes"].update(adminEventsExpiration="0"),
            id="admin-retention",
        ),
    ],
)
def test_k01_one_change_mutations_are_rejected(realm: dict[str, Any], mutation: Any) -> None:
    mutated = copy.deepcopy(realm)
    mutation(mutated)
    assert mutated != realm
    if (
        mutated["registrationAllowed"] != realm["registrationAllowed"]
        or mutated["bruteForceProtected"] != realm["bruteForceProtected"]
    ):
        with pytest.raises(AssertionError):
            test_k01_registration_broker_and_brute_force_configuration(mutated)
    elif mutated["accessTokenLifespan"] != realm["accessTokenLifespan"]:
        with pytest.raises(AssertionError):
            test_k01_access_token_lifespan_leaves_a_positive_remainder(mutated)
    else:
        with pytest.raises(AssertionError):
            test_k01_event_configuration_and_exact_retention(mutated)


def test_k01_direct_access_and_email_scope_mutations_change_guarded_values(
    realm: dict[str, Any],
) -> None:
    direct = copy.deepcopy(realm)
    direct["clients"][0]["directAccessGrantsEnabled"] = True
    assert not all(item.get("directAccessGrantsEnabled") is False for item in direct["clients"])
    scoped = copy.deepcopy(realm)
    application = client(scoped, "eko-backend")
    application["defaultClientScopes"].append("email")
    assert "email" in application["defaultClientScopes"]


def test_k01_adding_view_events_breaks_the_exact_composite(realm: dict[str, Any]) -> None:
    mutated = copy.deepcopy(realm)
    administrator = next(
        item
        for item in mutated["roles"]["client"]["eko-backend"]
        if item["name"] == "administrator"
    )
    administrator["composites"]["client"]["realm-management"].append("view-events")
    assert set(administrator["composites"]["client"]["realm-management"]) != ADMIN_COMPOSITE


def test_k01_export_path_is_inside_identity() -> None:
    assert EXPORT.parent == REPO_ROOT / "identity"
    assert EXPORT.suffix == ".json"
    assert Path(EXPORT.name).name == "eko-realm.json"
