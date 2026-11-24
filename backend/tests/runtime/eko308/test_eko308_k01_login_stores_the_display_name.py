"""EKO-3-08 K-01 (ADR-0003 *Staff personal data*, ADR-0003-C13; ADR-0003-C37, first sentence, in
the accepted addendum draft): each successful login stores or refreshes one display-name copy for
the caller's subject, holding only the subject, the NFC of the access token's `name`, whether the
token held `rep`, and the login instant from the injected clock. A refused login callback and a
token refresh write nothing; the copy is written in the transaction that creates the session.
"""

import threading
import unicodedata
from datetime import timedelta
from typing import Any

import pytest

from tests.runtime.eko201.conftest import refused_at_callback
from tests.runtime.eko308.conftest import (
    COPY_COLUMNS,
    COPY_TABLE,
    R1,
    R2,
    SESSION,
    Copy,
    Staff,
    copies,
    raw_copy_rows,
)
from tests.support import oidc_stub

pytestmark = pytest.mark.runtime

FIRST = "Anna Testowa"
SECOND = "Anna Nowak-Testowa"
# Synthetic markers in claims the copy must never hold.
MARKERS = {
    "given_name": "markerk01given",
    "family_name": "markerk01family",
    "sid": "markerk01sid",
    "session_state": "markerk01state",
    "acr": "markerk01acr",
    "eko_unknown_claim": "markerk01unknown",
}


def far_from(staff: Staff) -> dict[str, int]:
    """`iat` and `auth_time` 30 days before the clock: the stored instant must be the clock's."""
    far = int((staff.clock.now() - timedelta(days=30)).timestamp())
    return {"iat": far, "auth_time": far}


def test_k01_a_login_stores_one_copy_and_a_later_login_replaces_it(staff: Staff) -> None:
    t1 = staff.clock.now()
    staff.login(R1, ["rep"], FIRST, **MARKERS, **far_from(staff))
    assert copies(staff.pg) == {R1: Copy(FIRST, True, t1)}
    staff.clock.advance(hours=3)
    t2 = staff.clock.now()
    staff.login(R1, ["manager"], SECOND, **MARKERS, **far_from(staff))
    assert copies(staff.pg) == {R1: Copy(SECOND, False, t2)}


def test_k01_the_copy_holds_no_other_claim_and_no_role_name(staff: Staff) -> None:
    staff.login(R1, ["rep", "manager", "administrator"], FIRST, **MARKERS)
    [[stored]] = raw_copy_rows(staff.pg)
    assert R1 in stored and FIRST in stored
    # `rep` is the name of the column `is_rep`, so only the other two role names are looked for.
    for marker in [*MARKERS.values(), "manager", "administrator"]:
        assert marker not in stored, marker


def test_k01_the_copy_table_has_exactly_the_four_columns(staff: Staff) -> None:
    columns = staff.pg.rows(
        "SELECT column_name, data_type, collation_name, column_default, is_nullable "
        "FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
        (COPY_TABLE,),
    )
    assert tuple(c[0] for c in columns) == COPY_COLUMNS
    shape = {c[0]: c[1:] for c in columns}
    assert shape["subject"] == ("text", "C", None, "NO")
    assert shape["display_name"] == ("text", None, None, "YES")
    assert shape["is_rep"] == ("boolean", None, None, "NO")
    assert shape["last_login_at"] == ("timestamp with time zone", None, None, "NO")
    # One copy per subject: the subject is the key.
    [[key]] = staff.pg.rows(
        "SELECT string_agg(a.attname, ',') FROM pg_index i JOIN pg_attribute a "
        "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = %s::regclass AND i.indisprimary",
        (COPY_TABLE,),
    )
    assert key == "subject"


def test_k01_contrast_another_subject_adds_a_second_copy(staff: Staff) -> None:
    t1 = staff.clock.now()
    staff.login(R1, ["rep"], FIRST)
    staff.clock.advance(minutes=5)
    staff.login(R2, ["manager"], SECOND)
    assert copies(staff.pg) == {
        R1: Copy(FIRST, True, t1),
        R2: Copy(SECOND, False, t1 + timedelta(minutes=5)),
    }


@pytest.mark.parametrize(
    ("where", "claim", "value"),
    [
        pytest.param("id", "nonce", "markerk01-wrong-nonce", id="wrong-nonce"),
        pytest.param("access", "email", "synthetic.rep@example.invalid", id="email-in-access"),
        pytest.param("id", "email", "synthetic.rep@example.invalid", id="email-in-id"),
    ],
)
def test_k01_a_refused_callback_writes_nothing_and_the_valid_one_writes(
    staff: Staff, where: str, claim: str, value: str
) -> None:
    staff.login(R2, ["rep"], SECOND)
    before = raw_copy_rows(staff.pg)
    assert before, "the first login stored no copy"
    staff.stub.access_overrides = {"name": FIRST}
    overrides = staff.stub.access_overrides if where == "access" else staff.stub.id_overrides
    overrides[claim] = value
    staff.stub.next_user = oidc_stub.User(sub=R1, client_roles=["rep"])
    browser = staff.crm.open_browser(staff.app)
    assert refused_at_callback(browser.login())
    assert raw_copy_rows(staff.pg) == before
    overrides.pop(claim)
    assert browser.login().status_code == 303
    assert copies(staff.pg)[R1] == Copy(FIRST, True, staff.clock.now())


def test_k01_a_token_refresh_writes_nothing(staff: Staff) -> None:
    browser = staff.login(R1, ["rep"], FIRST)
    before = raw_copy_rows(staff.pg)
    assert before, "the login stored no copy: the comparison below would be vacuous"
    # The refreshed token carries another name and no `rep`; the copy stays as the login left it.
    staff.stub.access_overrides = {"name": SECOND}
    for session in staff.stub.sessions.values():
        session.user.client_roles = ["manager"]
    staff.clock.advance(seconds=staff.stub.access_lifespan_seconds + 1)
    refreshed = staff.stub.refreshes()
    assert browser.send("GET", SESSION).status_code == 200
    assert len(staff.stub.refreshes()) == len(refreshed) + 1, "no refresh happened"
    assert raw_copy_rows(staff.pg) == before


# Edges ---------------------------------------------------------------------------------------


def test_k01_edge_a_token_without_name_stores_a_copy_with_no_name(staff: Staff) -> None:
    browser = staff.login(R1, ["rep"], None)
    assert browser.send("GET", SESSION).status_code == 200
    assert copies(staff.pg) == {R1: Copy(None, True, staff.clock.now())}


@pytest.mark.parametrize(
    ("sent", "stored"),
    [
        pytest.param("Ż" * 300, "Ż" * 300, id="300-characters"),
        pytest.param(
            unicodedata.normalize("NFD", "Żaneta Łuczyńska-Gęś"), "Żaneta Łuczyńska-Gęś", id="nfd"
        ),
        pytest.param("Żaneta Łuczyńska-Gęś", "Żaneta Łuczyńska-Gęś", id="nfc-unchanged"),
        pytest.param("  Anna Testowa \t", "  Anna Testowa \t", id="spaces-kept"),
        pytest.param(
            unicodedata.normalize("NFD", " Zoë "), " Zoë ", id="nfd-with-spaces-not-trimmed"
        ),
    ],
)
def test_k01_edge_the_name_is_stored_whole_as_nfc_and_not_trimmed(
    staff: Staff, sent: str, stored: str
) -> None:
    assert unicodedata.is_normalized("NFC", stored)
    staff.login(R1, ["rep"], sent)
    assert copies(staff.pg)[R1].display_name == stored


def test_k01_edge_two_concurrent_logins_of_one_subject_leave_one_copy(staff: Staff) -> None:
    staff.stub.access_overrides = {"name": FIRST}
    staff.stub.next_user = oidc_stub.User(sub=R1, client_roles=["rep"])
    browsers = [staff.crm.open_browser(staff.app) for _ in range(2)]
    callbacks = [b.at_identity_server(b.start_login()) for b in browsers]
    answers: list[Any] = [None, None]
    start = threading.Barrier(2)

    def finish(index: int) -> None:
        start.wait()
        answers[index] = browsers[index].send("GET", callbacks[index])

    threads = [threading.Thread(target=finish, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert [a.status_code for a in answers] == [303, 303]
    assert not any(refused_at_callback(a) for a in answers)
    assert all(b.session is not None for b in browsers)
    assert copies(staff.pg) == {R1: Copy(FIRST, True, staff.clock.now())}


def test_k01_edge_a_callback_whose_session_write_fails_leaves_the_copy_store_unchanged(
    staff: Staff,
) -> None:
    staff.login(R2, ["rep"], SECOND)
    before = raw_copy_rows(staff.pg)
    assert before, "the first login stored no copy"
    with staff.pg.connect() as connection:
        connection.execute(
            "CREATE FUNCTION eko308_refuse() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'eko308 planted refusal'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER eko308_refuse BEFORE INSERT ON app_session "
            "FOR EACH ROW EXECUTE FUNCTION eko308_refuse()"
        )
    try:
        staff.stub.access_overrides = {"name": FIRST}
        staff.stub.next_user = oidc_stub.User(sub=R1, client_roles=["rep"])
        browser = staff.crm.open_browser(staff.app)
        assert refused_at_callback(browser.login())
        assert raw_copy_rows(staff.pg) == before
    finally:
        with staff.pg.connect() as connection:
            connection.execute("DROP TRIGGER eko308_refuse ON app_session")
            connection.execute("DROP FUNCTION eko308_refuse()")
    # Contrast: the same callback, once the session can be written, writes the copy.
    assert browser.login().status_code == 303
    assert R1 in copies(staff.pg)


@pytest.mark.parametrize(
    ("sent", "stored"),
    [
        pytest.param("Anna\x00Testowa", None, id="nul"),
        pytest.param("Anna \ud800Testowa", None, id="lone-surrogate"),
        pytest.param("Anna Testowa", "Anna Testowa", id="contrast-storable"),
    ],
)
def test_a11_a_name_postgresql_cannot_hold_is_stored_as_none_and_the_login_succeeds(
    staff: Staff, sent: str, stored: str | None
) -> None:
    """A-11 (human decision of 2026-11-23 on Issue #216)."""
    staff.stub.access_overrides = {"name": sent}
    staff.stub.next_user = oidc_stub.User(sub=R1, client_roles=["rep"])
    browser = staff.crm.open_browser(staff.app)
    answered = browser.login()
    assert answered.status_code == 303 and not refused_at_callback(answered)
    assert browser.session is not None
    assert copies(staff.pg) == {R1: Copy(stored, True, staff.clock.now())}
