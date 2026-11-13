"""EKO-2-01 against running Keycloak: a real staff login through the composition's callback.

K-02 (forwarded carrier): after a real login the decrypted stored access, refresh and ID tokens
carry neither `email` nor `preferred_username`, while the subject and name claims remain and the
account does hold an e-mail address in Keycloak (so the absence is the token configuration, not
missing data). The access token names `eko-backend` as audience and the public issuer, although
the backend fetched it over the back channel.
K-03 (backend/Keycloak half): an account with no linked Google or other identity provider logs
in and the backend recognises its new session; invalid company credentials create no session.
K-06 (Keycloak half of logout, G-2 A): logout deletes the application session and ends the
Keycloak SSO session, the old cookie gets 401, and a new login from the same browser cannot
reauthenticate silently; before logout, the same browser is reauthenticated silently.
"""

import secrets
from collections.abc import Iterator

import pytest

from tests.runtime import eko201_login as app
from tests.runtime.conftest import Started
from tests.runtime.keycloak_client import RealmClient
from tests.support import eko112_fixtures as eko112
from tests.support import eko201_keycloak as accounts

pytestmark = pytest.mark.runtime


@pytest.fixture
def master(keycloak_running: Started) -> Iterator[RealmClient]:
    client = RealmClient(keycloak_running.composition, "master")
    try:
        yield client
    finally:
        client.close()


def breakglass(master: RealmClient) -> str:
    env = master.composition.env
    return master.direct_master_token(
        eko112.ACCOUNTS["breakglass_one"], env[eko112.PASSWORD_VARIABLES["breakglass_one"]]
    )


def test_k02_k03_real_login_without_google_stores_tokens_without_email_or_username(
    keycloak_running: Started, master: RealmClient
) -> None:
    composition = keycloak_running.composition
    token = breakglass(master)
    password = "synthetic-" + secrets.token_urlsafe(24)
    user_id = app.ensure_staff_account(master, token, "login", password)
    # No identity provider exists and the account links none (ACC-2: no Google dependency).
    assert master.admin_json(token, "GET", "identity-provider/instances", realm="eko") == []
    assert master.admin_json(token, "GET", f"users/{user_id}/federated-identity", realm="eko") == []
    stored = master.admin_json(token, "GET", f"users/{user_id}", realm="eko")
    assert stored["email"] == accounts.ADDRESSES["login"], "the premise: Keycloak holds an e-mail"

    browser = RealmClient(composition, "eko", listener="auth")
    try:
        assert app.session_view(composition, "").status_code == 401
        before = app.session_count(composition)
        # Contrast first: invalid company credentials end on Keycloak's page, no callback, and
        # no application session appears.
        refused_start = app.start_login(composition)
        refused = app.at_keycloak(
            browser, refused_start, accounts.ACCOUNTS["login"], password + "-wrong"
        )
        assert refused.status_code == 200 and not app.is_callback_redirect(composition, refused)
        assert app.session_count(composition) == before

        session = app.login(composition, browser, accounts.ACCOUNTS["login"], password)
        assert app.session_count(composition) == before + 1
        view = app.session_view(composition, session)
        assert view.status_code == 200, view.status_code
        assert view.json() == {"subject": user_id, "name": accounts.DISPLAY_NAME}
    finally:
        browser.close()

    claims = app.stored_token_claims(composition)[-1]
    assert set(claims) == {"access", "refresh", "id"}
    for kind, values in claims.items():
        assert "email" not in values, f"{kind} token carries email"
        assert "preferred_username" not in values, f"{kind} token carries preferred_username"
        assert values["sub"] == user_id, f"{kind} token lost its subject"
        assert values["iss"] == app.issuer(composition), f"{kind} token issuer"
    for kind in ("access", "id"):
        assert claims[kind]["name"] == accounts.DISPLAY_NAME, f"{kind} token lost its name"
    audience = claims["access"]["aud"]
    assert "eko-backend" in ([audience] if isinstance(audience, str) else audience)


def test_k06_logout_ends_both_sessions_and_blocks_silent_reauthentication(
    keycloak_running: Started, master: RealmClient
) -> None:
    composition = keycloak_running.composition
    token = breakglass(master)
    password = "synthetic-" + secrets.token_urlsafe(24)
    user_id = app.ensure_staff_account(master, token, "logout", password)
    browser = RealmClient(composition, "eko", listener="auth")
    try:
        session = app.login(composition, browser, accounts.ACCOUNTS["logout"], password)
        assert app.session_view(composition, session).status_code == 200
        sso = master.admin_json(token, "GET", f"users/{user_id}/sessions", realm="eko")
        assert len(sso) == 1, "not exactly one Keycloak SSO session after login"

        # Contrast before logout: the same browser, holding Keycloak's SSO cookie, is logged
        # in again without any form (a redirect straight to the callback).
        silent_start = app.start_login(composition)
        silent = app.at_keycloak(browser, silent_start, "", "")
        assert app.is_callback_redirect(composition, silent), "SSO did not reauthenticate"
        second = app.finish_login(composition, silent_start, silent)
        assert second.status_code == 303
        second_session = app.set_cookies(second)[app.SESSION_COOKIE]

        before = app.session_count(composition)
        out = app.logout(composition, second_session)
        assert out.status_code == 200, out.status_code
        assert app.session_count(composition) == before - 1
        assert app.session_view(composition, second_session).status_code == 401
        # Repeated logout with the old cookie: 401, nothing else changes.
        assert app.logout(composition, second_session).status_code == 401
        assert master.admin_json(token, "GET", f"users/{user_id}/sessions", realm="eko") == []

        # After logout the same browser must see the login form again.
        again = app.start_login(composition)
        page = browser.request("GET", again.keycloak_path)
        assert page.status_code == 200, f"silent reauthentication after logout: {page.status_code}"
        assert 'name="password"' in page.text
        # The first application session belonged to the same ended SSO session; its own logout
        # ends it as well.
        assert app.logout(composition, session).status_code in (200, 401)
    finally:
        browser.close()
