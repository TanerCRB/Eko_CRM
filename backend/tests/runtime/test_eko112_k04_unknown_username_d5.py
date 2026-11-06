"""EKO-1-12 D-5: independently executed unknown-username privacy result."""

import secrets

import pytest

from tests.runtime.conftest import Started
from tests.runtime.keycloak_client import (
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
