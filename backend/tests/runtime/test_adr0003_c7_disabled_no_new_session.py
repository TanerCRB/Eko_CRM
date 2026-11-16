"""EKO-2-02 K-04 (ADR-0003-C7, *Account lifecycle*): a disabled account cannot obtain a new
session, and the application's rows naming its subject are untouched.

Against the running Keycloak configured by EKO-1-12 and the composition's own backend, through
the proxy: EKO-2-01's full login (start, Keycloak's form and one-time code, the callback). The
row is test-owned (a table the test creates and drops in the composition's database, never a
product revision). Keycloak's own refusal of a disabled account's refresh is EKO-1-12's
evidence and is not re-proven here.
"""

from collections.abc import Iterator

import httpx
import pytest

from tests.runtime import eko201_login as login_flow
from tests.runtime import eko202_live as live
from tests.runtime.conftest import Composition, Started
from tests.runtime.keycloak_client import RealmClient

pytestmark = pytest.mark.runtime

LOGIN_FAILED_PAGE = "/logowanie-nieudane"


@pytest.fixture
def composition(keycloak_running: Started) -> Iterator[Composition]:
    composition = keycloak_running.composition
    composition.sql(live.CREATE_RECORDS)
    try:
        yield composition
    finally:
        composition.sql(live.DROP_RECORDS)


def records(composition: Composition) -> list[list[str]]:
    return composition.sql(live.SELECT_RECORDS)


def keycloak_part(
    composition: Composition, username: str, password: str
) -> tuple[login_flow.LoginStart, httpx.Response]:
    """Login start through the backend, then Keycloak's part in a browser of its own."""
    start = login_flow.start_login(composition)
    browser = RealmClient(composition, "eko", listener="auth")
    try:
        return start, login_flow.at_keycloak(browser, start, username, password)
    finally:
        browser.close()


def test_k04_disabled_account_gets_no_session_and_its_rows_stay(
    composition: Composition,
) -> None:
    realm = live.Realm(composition)
    username, password = live.unique("k04"), live.new_password()
    user_id = realm.create_account(username, password, ["rep"])
    live.plant_in_composition(composition, user_id, "k04-owned")
    planted = records(composition)

    # Contrast: the identical flow with the account enabled creates a session for its subject.
    before = login_flow.session_count(composition)
    start, redirect = keycloak_part(composition, username, password)
    assert login_flow.is_callback_redirect(composition, redirect)
    session = login_flow.set_cookies(login_flow.finish_login(composition, start, redirect))[
        login_flow.SESSION_COOKIE
    ]
    assert login_flow.session_count(composition) == before + 1
    assert login_flow.session_view(composition, session).json()["subject"] == planted[0][1]

    # The one changed element: the account's enabled flag. Two attempts (a double submit).
    realm.set_enabled(user_id, False)
    before = login_flow.session_count(composition)
    for _ in range(2):
        start, ended = keycloak_part(composition, username, password)
        assert not login_flow.is_callback_redirect(composition, ended), "Keycloak issued a code"
        assert login_flow.session_count(composition) == before
    assert records(composition) == planted


def test_k04_disabled_between_login_start_and_callback_completes_no_session(
    composition: Composition,
) -> None:
    realm = live.Realm(composition)
    username, password = live.unique("k04-inflight"), live.new_password()
    user_id = realm.create_account(username, password, ["rep"])
    live.plant_in_composition(composition, user_id, "k04-inflight")
    planted = records(composition)

    start, redirect = keycloak_part(composition, username, password)
    assert login_flow.is_callback_redirect(composition, redirect), "no code issued while enabled"
    realm.set_enabled(user_id, False)
    before = login_flow.session_count(composition)
    # The in-flight callback, then the same callback again (a double submit).
    for _ in range(2):
        callback = login_flow.finish_login(composition, start, redirect)
        assert callback.status_code == 303, callback.status_code
        assert callback.headers["location"] == LOGIN_FAILED_PAGE
        assert login_flow.SESSION_COOKIE not in login_flow.set_cookies(callback)
        assert login_flow.session_count(composition) == before
    assert records(composition) == planted
