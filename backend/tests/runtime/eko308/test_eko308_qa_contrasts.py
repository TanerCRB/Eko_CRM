"""EKO-3-08 QA contrasts: carriers for criterion clauses whose first tests left a mutation alive.

- K-01, mutation (c): the copy written before the callback's checks. The refused-callback tests
  use a wrong `nonce` and an `email` claim; the `email` cases are refused already inside token
  verification (`oidc.py`, `_claims`), so they cannot fail when the write moves only past the
  callback's own checks. An ID token whose `sub` differs from the access token's is refused by
  the callback's own check (`sessions.py`, after the nonce), so the moved write is visible.
- K-05, mutation (c): the copy deleted when a login is refused. The existing test refuses the
  login of a browser holding no session, so the application never knows whose login was refused.
  Here the browser still holds its session when its next login is refused at the identity server.
- K-06, mutation (a): a display name logged when the login is refused. The K-06 run holds no
  refused login, so a name logged on the callback's refusal path reaches no captured record.

Every value is synthetic (ADR-0005).
"""

import logging
import unicodedata

import pytest

from tests.runtime.eko201.conftest import refused_at_callback
from tests.runtime.eko301.conftest import created_id
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import (
    backend_records,
    logged_text,
)
from tests.runtime.eko308.conftest import R1, R2, SESSION, Copy, Staff, copies, raw_copy_rows
from tests.support import log_lines as ll
from tests.support import oidc_stub

pytestmark = pytest.mark.runtime


def test_qa_k01_an_id_token_naming_another_subject_writes_no_copy(staff: Staff) -> None:
    staff.login(R2, ["rep"], "Robert Testowy")
    before = raw_copy_rows(staff.pg)
    assert before, "the first login stored no copy"
    staff.stub.access_overrides = {"name": "Anna Testowa"}
    staff.stub.id_overrides = {"sub": R2}
    staff.stub.next_user = oidc_stub.User(sub=R1, client_roles=["rep"])
    browser = staff.crm.open_browser(staff.app)
    assert refused_at_callback(browser.login())
    assert raw_copy_rows(staff.pg) == before
    # Contrast: the same callback with matching subjects writes R1's copy.
    staff.stub.id_overrides = {}
    assert browser.login().status_code == 303
    assert copies(staff.pg)[R1] == Copy("Anna Testowa", True, staff.clock.now())


def test_qa_k05_a_refused_login_of_a_browser_holding_a_session_changes_no_row(
    staff: Staff,
) -> None:
    browser = staff.login(R2, ["rep"], "Olga Testowa")
    created_id(browser, {"name": "Ferma QA K05"})
    assert browser.session is not None
    copy_before = raw_copy_rows(staff.pg)
    customers_before = staff.pg.rows("SELECT to_jsonb(c)::text FROM customer c ORDER BY id")
    assert copy_before and customers_before
    staff.stub.code_mode = "refuse"
    staff.clock.advance(hours=1)
    assert refused_at_callback(browser.login())
    assert raw_copy_rows(staff.pg) == copy_before
    assert staff.pg.rows("SELECT to_jsonb(c)::text FROM customer c ORDER BY id") == (
        customers_before
    )
    # Contrast: the same browser, the account not refused, logging in with a changed name.
    staff.stub.code_mode = "answer"
    staff.stub.access_overrides = {"name": "Olga Zmieniona"}
    staff.stub.next_user = oidc_stub.User(sub=R2, client_roles=["rep"])
    assert browser.login().status_code == 303
    assert copies(staff.pg)[R2].display_name == "Olga Zmieniona"


REFUSED_MARKER = "Zażółć Odmowa-QA"
REFUSED_FORMS = tuple(unicodedata.normalize(form, REFUSED_MARKER) for form in ("NFC", "NFD"))


@pytest.mark.parametrize(
    ("where", "claim", "value"),
    [
        pytest.param("id", "nonce", "markerqa-wrong-nonce", id="wrong-nonce"),
        pytest.param("id", "sub", R2, id="id-subject-differs"),
        pytest.param("access", "email", "synthetic.rep@example.invalid", id="email-in-access"),
    ],
)
def test_qa_k06_a_refused_login_logs_no_staff_name(
    staff: Staff, caplog: pytest.LogCaptureFixture, where: str, claim: str, value: str
) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    staff.stub.access_overrides = {"name": REFUSED_FORMS[1]}
    overrides = staff.stub.access_overrides if where == "access" else staff.stub.id_overrides
    overrides[claim] = value
    staff.stub.next_user = oidc_stub.User(sub=R1, client_roles=["rep"])
    browser = staff.crm.open_browser(staff.app)
    refused = browser.login()
    assert refused_at_callback(refused)
    assert not any(form in refused.text for form in REFUSED_FORMS)
    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    text = logged_text(caplog.records)
    for form in REFUSED_FORMS:
        assert ll.leaks(text, form) == [], form
    # Contrast: the same callback, not refused, does carry the name into the application.
    overrides.pop(claim)
    assert browser.login().status_code == 303
    assert browser.send("GET", SESSION).json()["name"] == REFUSED_FORMS[1]
