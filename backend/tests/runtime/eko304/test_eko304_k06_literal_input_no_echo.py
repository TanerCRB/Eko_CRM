"""EKO-3-04 K-06 (ADR-0005 *What may appear in logs*; ADR-0002 addendum of EKO-3-04, literal
matching; G-6 A; ADR-0003 addendum of EKO-3-04, Q-3 A): a query or filter value is matched
literally and never repeated. A pattern character, a quote, a backslash or an injection attempt is
answered 200 with exactly the customers holding it as text; a rejected `q` or `owner` gets a 422
naming its parameter and repeating no value; and no backend log record or PostgreSQL log line
written during the request holds a submitted value, refused or searched.

This is the in-process half: the backend's records through `caplog`, PostgreSQL's through the
throwaway server's own log, which runs the image's default settings (it logs a failed statement,
which the composition's PostgreSQL does not). The composition half, with `proxy`, is
`tests/runtime/test_eko304_k06_search_logs_through_proxy.py`.
"""

import logging
import secrets
import subprocess
import unicodedata
from typing import Any

import psycopg
import pytest
from psycopg import sql

from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_B, Crm
from tests.runtime.eko304.conftest import EMPTY, NOBODY, answer, customer, found, search
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
MARKER = f"markerk06{TOKEN}"
KEYS = {"loc", "msg", "type", "ctx"}


@pytest.fixture
def owned(crm: Crm) -> dict[str, Any]:
    rep = crm.login(REP_A, ["rep"])
    return {
        "rep": rep,
        "percent": customer(rep, "Sklep 100% Eko"),
        "quote": customer(rep, "O'Neill Farma"),
        "underscore": customer(rep, "Pole a_b"),
        "plain": customer(rep, "Zwykły"),
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("%", "percent", id="percent"),
        pytest.param("_", "underscore", id="underscore"),
        pytest.param("'", "quote", id="quote"),
        pytest.param("Zwykły", "plain", id="contrast-plain"),
    ],
)
def test_k06_a_special_character_is_matched_as_text(
    owned: dict[str, Any], query: str, expected: str
) -> None:
    assert found(owned["rep"], {"q": query}) == {owned[expected]}


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("\\", id="backslash"),
        pytest.param("%' OR '1'='1", id="injection"),
        pytest.param("%%", id="two-percents"),
        pytest.param("\\%", id="escaped-percent"),
    ],
)
def test_k06_a_pattern_or_injection_matches_nothing_here_and_is_answered_200(
    owned: dict[str, Any], query: str
) -> None:
    response = search(owned["rep"], {"q": query})
    assert response.status_code == 200, response.text
    assert response.json() == EMPTY


def test_k06_contrast_a_backslash_is_matched_where_it_is_stored(owned: dict[str, Any]) -> None:
    held = customer(owned["rep"], "Ferma a\\b")
    assert found(owned["rep"], {"q": "\\"}) == {held}
    assert found(owned["rep"], {"q": "a\\b"}) == {held}


# Rejected values and the logs --------------------------------------------------------------------


def pg_log(crm: Crm) -> str:
    result = subprocess.run(
        ["docker", "logs", crm.pg.container],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout + result.stderr


# The test's own HTTP client, playing the browser: it writes the URL it requested, query included.
CLIENT_LOGGERS = ("httpx", "httpcore")


def backend_records(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if r.name.split(".")[0] not in CLIENT_LOGGERS]


def logged_text(records: list[logging.LogRecord]) -> str:
    formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(formatter.format(r) + " " + repr(vars(r)) for r in backend_records(records))


def errors_of(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 422, response.text[:300]
    errors: list[dict[str, Any]] = response.json()["detail"]
    for error in errors:
        assert set(error) <= KEYS, error.keys()
    return errors


REJECTED: dict[str, tuple[dict[str, str], list[str]]] = {
    "query-over-the-bound": ({"q": MARKER + "q" * 254}, ["query", "q"]),
    "query-over-the-raw-cap": ({"q": MARKER + " " * 1100}, ["query", "q"]),
    "query-with-nul": ({"q": MARKER + "\x00"}, ["query", "q"]),
    "owner-over-the-bound": ({"owner": MARKER + "o" * 256}, ["query", "owner"]),
    "owner-with-a-space": ({"owner": MARKER + " x"}, ["query", "owner"]),
    "owner-not-ascii": ({"owner": MARKER + "ł"}, ["query", "owner"]),
}


@pytest.mark.parametrize("case", sorted(REJECTED))
def test_k06_a_rejected_value_is_named_by_its_parameter_and_never_repeated(
    crm: Crm, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    params, loc = REJECTED[case]
    rep = crm.login(REP_A, ["rep"])
    customer(rep, "Ferma Testowa")
    before = pg_log(crm)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    response = search(rep, params)
    assert [error["loc"] for error in errors_of(response)] == [loc]
    assert MARKER not in response.text
    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    assert ll.leaks(logged_text(caplog.records), MARKER) == []
    assert ll.leaks(pg_log(crm)[len(before) :], MARKER) == []


def test_k06_a_rejected_owner_is_answered_alike_for_a_rep_and_a_manager(crm: Crm) -> None:
    params = REJECTED["owner-over-the-bound"][0]
    rep = search(crm.login(REP_A, ["rep"]), params)
    manager = search(crm.login(MANAGER, ["manager"]), params)
    assert answer(rep) == answer(manager)


def test_k06_a_searched_value_reaches_no_log(crm: Crm, caplog: pytest.LogCaptureFixture) -> None:
    rep = crm.login(REP_A, ["rep"])
    held = customer(rep, f"Ferma {MARKER}")
    before = pg_log(crm)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    assert found(rep, {"q": MARKER}) == {held}
    assert found(rep, {"q": MARKER + "zz", "owner": REP_A}) == set()
    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    assert ll.leaks(logged_text(caplog.records), MARKER) == []
    assert ll.leaks(pg_log(crm)[len(before) :], MARKER) == []


def test_k06_contrast_only_the_test_clients_own_records_are_left_out(
    crm: Crm, caplog: pytest.LogCaptureFixture
) -> None:
    """The client's record holds the marker; the backend's request record is still captured."""
    rep = crm.login(REP_A, ["rep"])
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    search(rep, {"q": MARKER})
    kept = backend_records(caplog.records)
    left_out = [r for r in caplog.records if r not in kept]
    assert ll.leaks(repr([vars(r) for r in left_out]), MARKER) == [MARKER]
    assert any(r.name.startswith("app") and r.getMessage() == "request" for r in kept), kept
    assert ll.leaks(logged_text(caplog.records), MARKER) == []


def test_k06_contrast_the_postgresql_capture_sees_a_failed_statement(crm: Crm) -> None:
    """The throwaway server writes a failed statement's text: the window above can see one."""
    before = pg_log(crm)
    with crm.pg.connect() as connection:
        with pytest.raises(psycopg.errors.UndefinedTable):
            connection.execute(sql.SQL("SELECT 1 FROM {}").format(sql.Identifier(MARKER)))
    assert ll.leaks(pg_log(crm)[len(before) :], MARKER) != []


# Edges ---------------------------------------------------------------------------------------


def test_k06_edge_the_query_bound_is_254_code_points_after_trim_and_nfc(crm: Crm) -> None:
    """G-6 A: 254 code points pass and 255 do not; an NFD form whose NFC is 254 passes."""
    rep = crm.login(REP_A, ["rep"])
    customer(rep, "Ferma Testowa")
    assert search(rep, {"q": "  " + "ą" * 254 + "  "}).status_code == 200
    decomposed = unicodedata.normalize("NFD", "ą")
    assert len(decomposed) == 2
    assert search(rep, {"q": decomposed * 254}).status_code == 200
    assert search(rep, {"q": "ą" * 255}).status_code == 422
    assert search(rep, {"q": "x" * 1017}).status_code == 422


def test_k06_edge_the_owner_bound_is_255_printable_ascii_characters(crm: Crm) -> None:
    """Q-3 A: 255 characters in U+0021..U+007E pass and 256 do not."""
    manager = crm.login(MANAGER, ["manager"])
    assert search(manager, {"owner": "!~" * 127 + "a"}).status_code == 200
    assert search(manager, {"owner": "a" * 256}).status_code == 422
    assert search(manager, {"owner": "a\x7f"}).status_code == 422


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("q=%FF", id="invalid-utf-8"),
        pytest.param("q=a%C3", id="truncated-utf-8"),
        pytest.param("q=%ED%A0%80", id="encoded-surrogate"),
        pytest.param("owner=%FF", id="owner-invalid-utf-8"),
    ],
)
def test_k06_edge_invalid_percent_encoded_utf_8_gets_a_4xx_never_500(
    owned: dict[str, Any], raw: str
) -> None:
    response = owned["rep"].send("GET", f"/api/customers?{raw}")
    assert 400 <= response.status_code < 500, response.status_code
    assert "�" not in response.text
    assert raw.split("=", 1)[1] not in response.text


def test_k06_edge_a_repeated_query_gets_one_deterministic_answer(owned: dict[str, Any]) -> None:
    pairs = [("q", "sklep"), ("q", "zwykły")]
    first, second = search(owned["rep"], pairs), search(owned["rep"], pairs)
    assert first.status_code == 200, first.text
    assert answer(first) == answer(second)


def test_k06_edge_a_repeated_owner_never_differs_by_whether_the_owner_exists(
    crm: Crm, owned: dict[str, Any]
) -> None:
    customer(crm.login(REP_B, ["rep"]), "Ferma B1")
    rep = owned["rep"]
    for mine_at in (0, 1):
        existing = [("owner", REP_B)]
        missing = [("owner", NOBODY)]
        existing.insert(mine_at, ("owner", REP_A))
        missing.insert(mine_at, ("owner", REP_A))
        assert answer(search(rep, existing)) == answer(search(rep, missing)), mine_at
