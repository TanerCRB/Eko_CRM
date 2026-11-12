"""EKO-2-01 K-02 (ADR-0003-C8, backend half of C20): tokens stay server-side; the login callback is
bound to its transaction; login rotates the session; state-changing requests need the own Origin.

The decrypted-claims-after-real-login half of K-02 needs the running Keycloak and is carried by
developer-infrastructure; here the stub issues the tokens, so the backend's own refusal of a token
carrying `email` or `preferred_username` is what is shown.
"""

import urllib.parse
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import (
    LOGIN_COOKIE,
    ORIGIN,
    SESSION_COOKIE,
    AppFactory,
    FakeClock,
    session_count,
    set_cookies,
    transaction_count,
)
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

CALLBACK = f"{ORIGIN}/api/auth/callback"


def issued_tokens(stub: oidc_stub.Stub) -> list[str]:
    return list(stub.issued)


def test_k02_cookies_carry_prefix_and_attributes_and_no_token_reaches_the_browser(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    browser = browser_for(make_app())
    start = browser.start_login("/customers")
    [login_cookie] = set_cookies(start)
    assert login_cookie.name == LOGIN_COOKIE
    assert {"httponly", "secure", "path"} <= set(login_cookie.attributes)
    assert login_cookie.attributes["samesite"].lower() == "lax"
    assert login_cookie.attributes["path"] == "/"
    assert "domain" not in login_cookie.attributes
    assert 0 < int(login_cookie.attributes["max-age"]) <= 600
    done = browser.send("GET", browser.at_identity_server(start))
    assert done.status_code == 303, done.text
    assert done.headers["location"] == "/customers"
    cookies = {c.name: c for c in set_cookies(done)}
    assert set(cookies) == {SESSION_COOKIE, LOGIN_COOKIE}
    assert cookies[LOGIN_COOKIE].cleared
    session = cookies[SESSION_COOKIE]
    assert {"httponly", "secure"} <= set(session.attributes)
    assert session.attributes["samesite"].lower() == "strict"
    assert session.attributes["path"] == "/"
    assert "domain" not in session.attributes
    browser.send("GET", "/api/auth/session")
    browser.send("POST", "/api/auth/logout")
    tokens = issued_tokens(stub)
    assert len(tokens) == 3
    seen_names = set()
    for response in browser.responses:
        for cookie in set_cookies(response):
            seen_names.add(cookie.name)
            assert all(token not in cookie.value for token in tokens)
        assert all(token not in response.text for token in tokens), response.request.url
        assert all(token not in str(response.headers) for token in tokens)
    assert seen_names == {SESSION_COOKIE, LOGIN_COOKIE}


def test_k02_tokens_are_stored_encrypted(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    browser_for(make_app()).login()
    [[stored]] = pg.rows("SELECT tokens FROM app_session")
    assert all(token.encode() not in bytes(stored) for token in issued_tokens(stub))
    assert b"eyJ" not in bytes(stored)


def test_k02_authorization_request_binds_state_nonce_and_pkce(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub
) -> None:
    browser = browser_for(make_app())
    start = browser.start_login()
    target = urllib.parse.urlsplit(start.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == (
        f"{stub.issuer}/protocol/openid-connect/auth"
    )
    query = dict(urllib.parse.parse_qsl(target.query))
    assert query["response_type"] == "code"
    assert query["client_id"] == oidc_stub.CLIENT_ID
    assert query["redirect_uri"] == CALLBACK
    assert "openid" in query["scope"].split()
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) == 43
    assert len(query["state"]) >= 32 and len(query["nonce"]) >= 32
    assert query["state"] not in browser.jar[LOGIN_COOKIE]


def _refusal(browser: Any, path: str, pg: Postgres) -> None:
    answer = browser.send("GET", path)
    assert answer.status_code == 400, answer.text
    assert SESSION_COOKIE not in {c.name for c in set_cookies(answer)}
    assert any(c.name == LOGIN_COOKIE and c.cleared for c in set_cookies(answer)), answer.headers
    assert session_count(pg) == 0
    assert transaction_count(pg) == 0


def _with_state(path: str, state: str | None) -> str:
    split = urllib.parse.urlsplit(path)
    query = dict(urllib.parse.parse_qsl(split.query))
    if state is None:
        query.pop("state")
    else:
        query["state"] = state
    return f"{split.path}?{urllib.parse.urlencode(query)}"


@pytest.mark.parametrize("state", [None, "", "null", "mismatched-" + "s" * 40])
def test_k02_callback_with_missing_empty_null_or_mismatched_state_is_refused(
    make_app: AppFactory, browser_for: Any, pg: Postgres, state: str | None
) -> None:
    browser = browser_for(make_app())
    path = browser.at_identity_server(browser.start_login())
    _refusal(browser, _with_state(path, state), pg)
    # Contrast: the same transaction's cookie with the right state would have succeeded, so a
    # fresh login with only the state left intact does.
    assert browser.login().status_code == 303
    assert session_count(pg) == 1


def test_k02_callback_without_the_transaction_cookie_is_refused(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    path = browser.at_identity_server(browser.start_login())
    browser.jar.pop(LOGIN_COOKIE)
    answer = browser.send("GET", path)
    assert answer.status_code == 400
    assert session_count(pg) == 0


def test_k02_two_transactions_with_swapped_states_are_refused(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    app = make_app()
    first, second = browser_for(app), browser_for(app)
    first_path = first.at_identity_server(first.start_login())
    second_path = second.at_identity_server(second.start_login())
    first_state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(first_path).query))["state"]
    answer = second.send("GET", _with_state(second_path, first_state))
    assert answer.status_code == 400
    assert session_count(pg) == 0
    # The first transaction is untouched by the second browser's refused callback.
    assert first.send("GET", first_path).status_code == 303
    assert session_count(pg) == 1


@pytest.mark.parametrize(("age", "accepted"), [(599, True), (600, False), (601, False)])
def test_k02_transaction_validity_is_at_most_ten_minutes(
    make_app: AppFactory,
    browser_for: Any,
    clock: FakeClock,
    pg: Postgres,
    age: int,
    accepted: bool,
) -> None:
    browser = browser_for(make_app())
    path = browser.at_identity_server(browser.start_login())
    clock.advance(seconds=age)
    answer = browser.send("GET", path)
    assert answer.status_code == (303 if accepted else 400), answer.text
    assert session_count(pg) == (1 if accepted else 0)
    assert transaction_count(pg) == 0


def test_k02_replayed_callback_creates_no_second_session(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    start = browser.start_login()
    login_cookie = browser.jar[LOGIN_COOKIE]
    path = browser.at_identity_server(start)
    assert browser.send("GET", path).status_code == 303
    assert session_count(pg) == 1
    browser.jar.pop(SESSION_COOKIE)
    browser.jar[LOGIN_COOKIE] = login_cookie
    assert browser.send("GET", path).status_code == 400
    assert session_count(pg) == 1


def test_k02_out_of_order_callback_after_a_newer_login_start_is_refused(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    old_path = browser.at_identity_server(browser.start_login())
    new_path = browser.at_identity_server(browser.start_login())
    assert browser.send("GET", old_path).status_code == 400
    assert session_count(pg) == 0
    assert browser.send("GET", new_path).status_code == 400


def test_k02_nonce_mismatch_in_the_id_token_is_refused(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    stub.id_overrides["nonce"] = "other-nonce-" + "n" * 30
    browser = browser_for(make_app())
    assert browser.login().status_code == 400
    assert session_count(pg) == 0


def test_k02_identity_server_refusing_the_code_creates_no_session(
    make_app: AppFactory, browser_for: Any, stub: oidc_stub.Stub, pg: Postgres
) -> None:
    stub.code_mode = "refuse"
    browser = browser_for(make_app())
    assert browser.login().status_code == 400
    assert session_count(pg) == 0
    assert transaction_count(pg) == 0


def test_k02_error_answer_from_the_identity_server_is_refused(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    browser = browser_for(make_app())
    browser.start_login()
    answer = browser.send("GET", "/api/auth/callback?error=access_denied&state=x")
    assert answer.status_code == 400
    assert session_count(pg) == 0
    assert transaction_count(pg) == 0


def test_k02_login_creates_a_fresh_identifier_and_deletes_the_presented_session(
    make_app: AppFactory, browser_for: Any, pg: Postgres
) -> None:
    app = make_app()
    browser = browser_for(app)
    browser.login()
    old = browser.session
    assert old is not None
    assert browser.login().status_code == 303
    new = browser.session
    assert new is not None and new != old
    assert session_count(pg) == 1
    replay = browser_for(app)
    replay.jar[SESSION_COOKIE] = old
    assert replay.send("GET", "/api/auth/session").status_code == 401
    assert browser.send("GET", "/api/auth/session").status_code == 200


@pytest.mark.parametrize("origin", [None, "null", "https://evil.test", "http://app.test", ""])
def test_k02_state_changing_request_without_the_own_origin_is_refused(
    make_app: AppFactory, browser_for: Any, pg: Postgres, origin: str | None
) -> None:
    browser = browser_for(make_app())
    browser.login()
    headers = {} if origin is None else {"origin": origin}
    refused = browser.send("POST", "/api/auth/logout", origin=None, headers=headers)
    assert refused.status_code == 403, refused.text
    assert session_count(pg) == 1
    # Contrast: only the header changed to the application's own origin.
    assert browser.send("POST", "/api/auth/logout").status_code == 200
    assert session_count(pg) == 0


@pytest.mark.parametrize(
    ("where", "claim"),
    [("access", "email"), ("access", "preferred_username"), ("id", "email"),
     ("id", "preferred_username")],
)  # fmt: skip
def test_k02_token_carrying_email_or_username_is_not_stored(
    make_app: AppFactory,
    browser_for: Any,
    stub: oidc_stub.Stub,
    pg: Postgres,
    where: str,
    claim: str,
) -> None:
    overrides = stub.access_overrides if where == "access" else stub.id_overrides
    overrides[claim] = "synthetic.rep@example.invalid"
    browser = browser_for(make_app())
    assert browser.login().status_code == 400
    assert session_count(pg) == 0
    # Contrast: the approved name claims alone are stored and reach the session answer.
    overrides.pop(claim)
    assert browser.login().status_code == 303
    answer = browser.send("GET", "/api/auth/session").json()
    assert answer["name"] == "Synthetic Rep"


def test_k02_return_destination_outside_the_application_falls_back_to_root(
    make_app: AppFactory, browser_for: Any
) -> None:
    for unsafe in ("https://evil.test/", "//evil.test/x", "/\\evil.test", "/api/auth/logout"):
        browser = browser_for(make_app())
        assert browser.login(unsafe).headers["location"] == "/", unsafe


def test_k02_no_cookie_other_than_the_two_is_ever_set(
    make_app: AppFactory, browser_for: Any
) -> None:
    browser = browser_for(make_app())
    browser.send("GET", "/api/health")
    browser.login()
    browser.send("GET", "/api/auth/session")
    browser.send("POST", "/api/auth/logout")
    names = {c.name for r in browser.responses for c in set_cookies(r)}
    assert names == {SESSION_COOKIE, LOGIN_COOKIE}
    assert all(isinstance(r, httpx.Response) for r in browser.responses)
