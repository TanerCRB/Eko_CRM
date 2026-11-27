"""EKO-4-01 K-03 (ADR-0002 *Wall time entered by a user*, ADR-0002-C15; ADR-0001 Constraint 3): the
server resolves the typed Europe/Warsaw wall times to instants and refuses invalid visit values
with their reason, storing nothing.

Every scenario sends the request to the API directly. The stored instant is read back twice: the
by-id answer and the `timestamptz` value itself. A refusal for a time the clocks skip or repeat
names its own reason as the error's `type`, at the field (`start` or `end`), and repeats no value.
Runtime, on real PostgreSQL and the OIDC stub; every value is synthetic.
"""

import json
import unicodedata
from datetime import UTC, datetime
from typing import Any

import pytest

from tests.runtime.eko201.conftest import FakeClock
from tests.runtime.eko301.conftest import REP_A, Crm
from tests.runtime.eko401.conftest import (
    customer,
    plan,
    planned,
    read_visit,
    stored_visit,
    visit_body,
    visit_count,
    wall,
)

pytestmark = pytest.mark.runtime

NONEXISTENT = "nonexistent_local_time"
AMBIGUOUS = "ambiguous_local_time"


def instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def errors(response: Any) -> list[tuple[str, list[Any]]]:
    assert response.status_code == 422, response.text[:500]
    return [(e["type"], e["loc"]) for e in response.json()["detail"]]


@pytest.fixture
def own(crm: Crm) -> tuple[Any, str]:
    rep_a = crm.login(REP_A, ["rep"])
    return rep_a, customer(rep_a, "Gospodarstwo K03")


NEIGHBOURS = {
    "autumn-01:30-to-03:30": (
        ("2026-10-25", "01:30"),
        ("2026-10-25", "03:30"),
        "2026-10-24T23:30:00Z",
        "2026-10-25T02:30:00Z",
    ),
    "spring-03:00": (
        ("2026-03-29", "03:00"),
        ("2026-03-29", "04:00"),
        "2026-03-29T01:00:00Z",
        "2026-03-29T02:00:00Z",
    ),
}


@pytest.mark.parametrize("case", sorted(NEIGHBOURS))
def test_k03_the_unambiguous_neighbours_resolve_to_the_instants_c15_fixes(
    crm: Crm, own: tuple[Any, str], case: str
) -> None:
    rep_a, customer_id = own
    start, end, starts_at, ends_at = NEIGHBOURS[case]
    created = planned(rep_a, visit_body(customer_id, start, end))
    assert (created["starts_at"], created["ends_at"]) == (starts_at, ends_at)
    assert read_visit(rep_a, created["id"]).json()["starts_at"] == starts_at
    row = stored_visit(crm.pg, created["id"])
    assert (row["starts_at"], row["ends_at"]) == (instant(starts_at), instant(ends_at))


# (start, end) with the DST hour at `field`; the other end is a valid time on the same day.
REFUSED = {
    ("ambiguous", "start"): (("2026-10-25", "02:30"), ("2026-10-25", "04:00"), AMBIGUOUS),
    ("ambiguous", "end"): (("2026-10-25", "01:00"), ("2026-10-25", "02:30"), AMBIGUOUS),
    ("nonexistent", "start"): (("2026-03-29", "02:30"), ("2026-03-29", "04:00"), NONEXISTENT),
    ("nonexistent", "end"): (("2026-03-29", "01:00"), ("2026-03-29", "02:30"), NONEXISTENT),
}


@pytest.mark.parametrize("case", sorted(REFUSED), ids=lambda c: "-".join(c))
def test_k03_a_time_the_clocks_skip_or_repeat_is_refused_naming_its_reason(
    crm: Crm, own: tuple[Any, str], case: tuple[str, str]
) -> None:
    rep_a, customer_id = own
    start, end, reason = REFUSED[case]
    response = plan(rep_a, visit_body(customer_id, start, end))
    assert errors(response) == [(reason, ["body", case[1]])]
    assert "02:30" not in response.text and "2026-" not in response.text
    assert visit_count(crm.pg) == 0


def test_k03_the_two_reasons_are_distinct(crm: Crm, own: tuple[Any, str]) -> None:
    rep_a, customer_id = own
    skipped = plan(rep_a, visit_body(customer_id, ("2026-03-29", "02:30"), ("2026-03-29", "04:00")))
    repeated = plan(
        rep_a, visit_body(customer_id, ("2026-10-25", "02:30"), ("2026-10-25", "04:00"))
    )
    [(skipped_type, _)], [(repeated_type, _)] = errors(skipped), errors(repeated)
    assert (skipped_type, repeated_type) == (NONEXISTENT, AMBIGUOUS)
    assert skipped.json()["detail"][0]["msg"] != repeated.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    ("day", "refused", "accepted", "starts_at"),
    [
        ("2026-10-25", "02:30", "03:30", "2026-10-25T02:30:00Z"),
        ("2026-03-29", "02:30", "03:00", "2026-03-29T01:00:00Z"),
    ],
)
def test_k03_contrast_moving_only_the_time_out_of_the_dst_hour_is_accepted(
    crm: Crm, own: tuple[Any, str], day: str, refused: str, accepted: str, starts_at: str
) -> None:
    rep_a, customer_id = own
    assert plan(rep_a, visit_body(customer_id, (day, refused), (day, "05:00"))).status_code == 422
    created = planned(rep_a, visit_body(customer_id, (day, accepted), (day, "05:00")))
    assert created["starts_at"] == starts_at
    assert visit_count(crm.pg) == 1


def test_k03_an_end_equal_to_or_before_the_start_is_refused_at_the_end(
    crm: Crm, own: tuple[Any, str]
) -> None:
    rep_a, customer_id = own
    day = "2026-11-30"
    for end in ("10:00", "09:59", "09:00"):
        response = plan(rep_a, visit_body(customer_id, (day, "10:00"), (day, end)))
        assert [loc for _, loc in errors(response)] == [["body", "end"]], end
    assert visit_count(crm.pg) == 0
    # Contrast: one minute after the start is accepted.
    planned(rep_a, visit_body(customer_id, (day, "10:00"), (day, "10:01")))


WRONG_FORMS: dict[str, tuple[Any, list[Any]]] = {
    "time-with-offset": (wall("2026-11-30", "10:00+02:00"), ["body", "start", "time"]),
    "time-with-zone": (wall("2026-11-30", "10:00Z"), ["body", "start", "time"]),
    "time-with-seconds": (wall("2026-11-30", "10:00:00"), ["body", "start", "time"]),
    "time-24:00": (wall("2026-11-30", "24:00"), ["body", "start", "time"]),
    "time-single-digit-hour": (wall("2026-11-30", "9:00"), ["body", "start", "time"]),
    "date-impossible": (wall("2026-02-30", "10:00"), ["body", "start", "date"]),
    "date-as-instant": (wall("2026-11-30T10:00:00Z", "10:00"), ["body", "start", "date"]),
    "instant-instead-of-wall-time": ("2026-11-30T09:00:00Z", ["body", "start"]),
    "number-instead-of-date": ({"date": 20261130, "time": "10:00"}, ["body", "start", "date"]),
}


@pytest.mark.parametrize("case", sorted(WRONG_FORMS))
def test_k03_edge_a_wall_time_in_any_other_form_is_refused(
    crm: Crm, own: tuple[Any, str], case: str
) -> None:
    rep_a, customer_id = own
    start, loc = WRONG_FORMS[case]
    body = visit_body(customer_id)
    body["start"] = start
    response = plan(rep_a, body)
    assert [found for _, found in errors(response)] == [loc]
    assert visit_count(crm.pg) == 0


def test_k03_edge_a_past_start_is_accepted_and_held_at_once(crm: Crm, own: tuple[Any, str]) -> None:
    rep_a, customer_id = own
    # The application's clock alone: the login's clock stays, so the session stays valid.
    crm.app.state.clock = FakeClock(datetime(2026, 11, 26, 12, 0, tzinfo=UTC))
    created = planned(
        rep_a, visit_body(customer_id, ("2026-11-20", "10:00"), ("2026-11-20", "11:00"))
    )
    assert created["state"] == "held"


def test_k03_edge_a_visit_may_cross_midnight(crm: Crm, own: tuple[Any, str]) -> None:
    rep_a, customer_id = own
    created = planned(
        rep_a, visit_body(customer_id, ("2026-11-30", "23:00"), ("2026-12-01", "01:00"))
    )
    assert (created["starts_at"], created["ends_at"]) == (
        "2026-11-30T22:00:00Z",
        "2026-12-01T00:00:00Z",
    )


@pytest.mark.parametrize("given", ["omitted", None, "", "   \t "])
def test_k03_edge_an_own_address_not_given_is_stored_as_none(
    crm: Crm, own: tuple[Any, str], given: str | None
) -> None:
    rep_a, customer_id = own
    body = visit_body(customer_id)
    if given != "omitted":
        body["own_address"] = given
    created = planned(rep_a, body)
    assert created["own_address"] is None
    assert stored_visit(crm.pg, created["id"])["own_address"] is None


def test_k03_edge_an_own_address_is_trimmed_stored_as_nfc_and_markup_as_text(
    crm: Crm, own: tuple[Any, str]
) -> None:
    rep_a, customer_id = own
    decomposed = unicodedata.normalize("NFD", "  Zażółć 7 <b>pole</b>  ")
    created = planned(rep_a, visit_body(customer_id, own_address=decomposed))
    expected = unicodedata.normalize("NFC", "Zażółć 7 <b>pole</b>")
    assert created["own_address"] == expected
    assert stored_visit(crm.pg, created["id"])["own_address"] == expected


def test_k03_edge_an_own_address_of_200_characters_is_accepted_and_201_refused(
    crm: Crm, own: tuple[Any, str]
) -> None:
    rep_a, customer_id = own
    marker = "Polna-k03-"
    accepted = marker + "a" * (200 - len(marker))
    assert planned(rep_a, visit_body(customer_id, own_address=accepted))["own_address"] == accepted
    # The bound is counted on the NFC form: 200 "ó" sent as NFD are 400 code points and fit.
    decomposed = unicodedata.normalize("NFD", "ó" * 200)
    composed = planned(rep_a, visit_body(customer_id, own_address=decomposed))
    assert composed["own_address"] == "ó" * 200
    for refused in (accepted + "a", marker + "x" * 900):
        response = plan(rep_a, visit_body(customer_id, own_address=refused))
        assert [loc for _, loc in errors(response)] == [["body", "own_address"]]
        assert marker not in response.text
    assert visit_count(crm.pg) == 2


def test_k03_edge_a_lone_surrogate_in_the_own_address_is_a_422(
    crm: Crm, own: tuple[Any, str]
) -> None:
    rep_a, customer_id = own
    # A JSON escape is the only way to send a lone surrogate; the UTF-8 body cannot hold one.
    body = json.dumps(visit_body(customer_id))[:-1] + ', "own_address": "ul. \\ud800"}'
    response = rep_a.send(
        "POST",
        "/api/visits",
        content=body.encode("ascii"),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert visit_count(crm.pg) == 0
