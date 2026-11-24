"""EKO-3-08 K-06 (ADR-0005 *What may appear in logs*; ACC-8; Issue Out of scope: `CustomerItem`
stays `{id, name, country}`; the accepted addendum draft: the retention run writes counts only):
no backend log record, error body or customer response carries a staff display name; only the
manager's reps list and the caller's own session read do. The owner filter never consults the
copy, so a subject with customers and no copy is filtered as before.
"""

import logging
import re
import unicodedata
from datetime import timedelta

import httpx
import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, created_id, customer_url
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import (
    backend_records,
    logged_text,
)
from tests.runtime.eko308.conftest import M2, R1, R2, REPS, SESSION, Staff, run_retention
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

MARKER = "Zażółć Markerowa-K06"
FORMS = (unicodedata.normalize("NFC", MARKER), unicodedata.normalize("NFD", MARKER))
assert FORMS[0] != FORMS[1]


def carries(response: httpx.Response) -> bool:
    return any(form in response.text for form in FORMS)


def test_k06_no_log_or_answer_but_two_carries_the_staff_name(
    staff: Staff, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    # A second marker subject logs in now and its copy is deleted by the retention run below.
    staff.login(R2, ["manager"], FORMS[1])
    staff.clock.advance(hours=1)
    rep = staff.login(R1, ["rep"], FORMS[1])
    manager = staff.login(M2, ["manager"], "Maria Kierownicza")
    created = rep.send("POST", CUSTOMERS, json={"name": "Ferma K06"})
    customer_id = created.json()["id"]
    others = [
        created,
        rep.send("GET", customer_url(customer_id)),
        rep.send("GET", CUSTOMERS),
        rep.send("GET", CUSTOMERS, params={"q": "Ferma"}),
        manager.send("GET", CUSTOMERS, params={"owner": R1}),
        manager.send("GET", CUSTOMERS, params={"owner": "not a subject"}),
        rep.send("GET", REPS),
        manager.send("GET", SESSION),
    ]
    assert [r.status_code for r in others] == [201, 200, 200, 200, 200, 422, 403, 200]
    for response in others:
        assert not carries(response), (response.request.url, response.text[:300])
    own_session = rep.send("GET", SESSION)
    reps = manager.send("GET", REPS)
    # Contrast: the marker did reach the application, in the two answers that may carry it.
    # The session read is the token's name as carried, never the copy's NFC (ADR-0003-C37).
    assert own_session.json()["name"] == FORMS[1]
    assert {e["name"] for e in reps.json()["items"]} == {FORMS[0]}

    staff.clock.at = staff.clock.now() + timedelta(hours=180 * 24) - timedelta(minutes=30)
    run_retention(staff.pg, staff.clock, monkeypatch)
    deleted = [r.getMessage() for r in caplog.records if "display-name copies" in r.getMessage()]
    assert len(deleted) == 1, deleted
    assert re.fullmatch(
        r"retention deleted \d+ sessions, \d+ login transactions and 1 display-name copies",
        deleted[0],
    ), deleted

    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    text = logged_text(caplog.records)
    for form in FORMS:
        assert ll.leaks(text, form) == [], form
    for subject in (R1, R2):
        assert subject not in "\n".join(deleted)


def test_k06_customer_answers_keep_their_shape(staff: Staff) -> None:
    rep = staff.login(R1, ["rep"], MARKER)
    customer_id = created_id(rep, {"name": "Ferma K06"})
    listed = rep.send("GET", CUSTOMERS).json()
    assert listed == {"items": [{"id": customer_id, "name": "Ferma K06", "country": "PL"}]}
    assert "owner" not in rep.send("GET", customer_url(customer_id)).json()


def test_k06_the_owner_filter_does_not_consult_the_copy(staff: Staff) -> None:
    rep = staff.login(R1, ["rep"], MARKER)
    owned = {created_id(rep, {"name": "Ferma K06 A"}), created_id(rep, {"name": "Ferma K06 B"})}
    with staff.pg.connect() as connection:
        connection.execute("TRUNCATE staff_display_name")
    manager = staff.login(M2, ["manager"], "Maria Kierownicza")
    with staff.pg.connect() as connection:
        connection.execute("DELETE FROM staff_display_name WHERE subject = %s", (M2,))
    answered = manager.send("GET", CUSTOMERS, params={"owner": R1})
    assert answered.status_code == 200
    assert {item["id"] for item in answered.json()["items"]} == owned
