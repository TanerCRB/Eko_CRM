"""EKO-3-01 fix round 2, QA contrasts for the 422 shape of decision D on Issue #195.

- Every string in an error is cut to 200 characters: an unknown key the caller chose comes back
  in `loc` at most that long.
- Unknown keys are refused with one error naming the first of them, however many there are
  (fix round 3, decision D and hard-stop-6 option B on Issue #195).
- A 422 names at most 50 errors, pinned through invalid contact fields: each contact
  `{"kind": "fax", "value": 1}` gives two errors (measured), so 24 contacts give 48, all named,
  and 25, 26 or 50 contacts give 50, 52 or 100, of which 50 are named.
- `ctx` of a `value_error` is the rule's fixed message as text, not the exception object.
- An unknown key holding a lone surrogate gets a 422 naming the body, not a 500: the key is
  refused as text before it can reach `loc`.
- For every error type these models produce from a value, the value never comes back: not in
  `msg`, not in `ctx`. Only `loc` names the field, and a key the caller chose is part of `loc`.

Every value is synthetic (ADR-0005).
"""

import json
from typing import Any

import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm

pytestmark = pytest.mark.runtime

KEYS = {"loc", "msg", "type", "ctx"}
MARKER = "echo-marker-qa-r01b"
NAME = "Gospodarstwo Granica"
PHONE = "601000001"


def rejected(crm: Crm, content: bytes) -> Any:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = rep.send(
        "POST", CUSTOMERS, content=content, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422, response.text[:300]
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert crm.counts() == before
    errors: list[dict[str, Any]] = response.json()["detail"]
    for error in errors:
        assert set(error) <= KEYS, error.keys()
    return response


def unknown_keys(count: int, key: str = "unknown_{}") -> bytes:
    body: dict[str, Any] = {"name": NAME}
    body.update({key.format(i): 1 for i in range(count)})
    return json.dumps(body).encode()


def test_qa_r01b_a_huge_unknown_key_comes_back_cut_to_200_characters(crm: Crm) -> None:
    key = "k" * 100_000
    response = rejected(crm, json.dumps({"name": NAME, key: 1}).encode())
    [error] = response.json()["detail"]
    assert (error["type"], error["loc"]) == ("extra_forbidden", ["body", "k" * 200])
    assert len(response.content) < 1024, len(response.content)


@pytest.mark.parametrize("count", [50, 51, 10_000])
def test_qa_r01b_unknown_keys_give_one_error_naming_the_first(crm: Crm, count: int) -> None:
    response = rejected(crm, unknown_keys(count))
    errors = response.json()["detail"]
    assert [(e["type"], e["loc"]) for e in errors] == [("extra_forbidden", ["body", "unknown_0"])]
    assert len(response.content) < 100 * 50, len(response.content)


def invalid_contacts(count: int) -> bytes:
    """`count` contacts, each refused on two fields, `kind` and `value` (measured)."""
    return json.dumps({"name": NAME, "contacts": [{"kind": "fax", "value": 1}] * count}).encode()


@pytest.mark.parametrize(("contacts", "named"), [(25, 50), (26, 50), (50, 50)])
def test_qa_r01b_a_422_names_at_most_50_errors(crm: Crm, contacts: int, named: int) -> None:
    response = rejected(crm, invalid_contacts(contacts))
    errors = response.json()["detail"]
    assert len(errors) == named
    assert {e["type"] for e in errors} == {"literal_error", "string_type"}
    assert len(response.content) < 150 * named, len(response.content)


def test_qa_r01b_contrast_fewer_errors_than_the_bound_are_all_named(crm: Crm) -> None:
    errors = rejected(crm, unknown_keys(3)).json()["detail"]
    assert [(e["type"], e["loc"]) for e in errors] == [("extra_forbidden", ["body", "unknown_0"])]
    known = rejected(crm, invalid_contacts(24)).json()["detail"]
    assert len(known) == 48
    assert sorted((e["loc"][2], e["loc"][3]) for e in known) == sorted(
        (n, field) for n in range(24) for field in ("kind", "value")
    )


def test_qa_r01b_a_value_error_ctx_is_the_rules_message_as_text(crm: Crm) -> None:
    response = rejected(crm, json.dumps({"name": NAME, "country": "XX"}).encode())
    [error] = response.json()["detail"]
    assert (error["type"], error["loc"]) == ("value_error", ["body", "country"])
    assert error["ctx"] == {"error": "not a country code of the list"}


def test_qa_r01b_a_lone_surrogate_in_an_unknown_key_gets_a_422_not_a_500(crm: Crm) -> None:
    response = rejected(crm, b'{"name": "Gospodarstwo", "\\ud800": 1}')
    [error] = response.json()["detail"]
    assert (error["type"], error["loc"]) == ("string_unicode", ["body"])


def contact(**fields: Any) -> dict[str, Any]:
    return {"name": NAME, "contacts": [{"kind": "phone", "value": PHONE, **fields}]}


VALUE_CASES = [
    pytest.param({"name": 5, "unknown": MARKER}, id="name-int-and-extra-value"),
    pytest.param({"name": [MARKER]}, id="name-list"),
    pytest.param({"name": NAME, "country": MARKER}, id="country-long"),
    pytest.param({"name": NAME, "contacts": MARKER}, id="contacts-str"),
    pytest.param({"name": NAME, "contacts": [MARKER]}, id="contact-str"),
    pytest.param(contact(kind=MARKER), id="kind-literal"),
    pytest.param(contact(value=[MARKER]), id="value-list"),
    pytest.param(contact(value=MARKER), id="phone-value"),
    pytest.param(contact(kind="email", value=MARKER), id="email-value"),
    pytest.param(contact(note=[MARKER]), id="note-list"),
    pytest.param(contact(primary=MARKER), id="primary-str"),
    pytest.param({"contacts": [{"kind": "email", "value": f"{MARKER}@b.cd"}]}, id="missing"),
    pytest.param([MARKER], id="body-list"),
    pytest.param(MARKER, id="body-str"),
]


@pytest.mark.parametrize("body", VALUE_CASES)
def test_qa_r01b_no_error_type_carries_the_value_in_msg_or_ctx(crm: Crm, body: Any) -> None:
    response = rejected(crm, json.dumps(body).encode())
    assert MARKER not in response.text
    for error in response.json()["detail"]:
        for value in error.get("ctx", {}).values():
            assert isinstance(value, int | float | bool | str), error


def test_qa_r01b_malformed_json_is_not_echoed(crm: Crm) -> None:
    response = rejected(crm, f'{{"name": "{MARKER}'.encode())
    [error] = response.json()["detail"]
    assert error["type"] == "json_invalid"
    assert MARKER not in response.text
