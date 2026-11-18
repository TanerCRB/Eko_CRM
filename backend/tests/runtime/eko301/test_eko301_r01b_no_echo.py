"""EKO-3-01 fix round 2, Reviewer R-01 remainder (decision D on Issue #195): a 422 for a rejected
request carries no `input` for any error type. Each error keeps only `loc`, `msg`, `type` and
`ctx`, and `ctx` holds only bounded constants, so neither a value the caller sent nor the body
itself comes back, and the rejected body is never walked to encode it.
"""

import json
from typing import Any

import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm

pytestmark = pytest.mark.runtime

KEYS = {"loc", "msg", "type", "ctx"}
MARKER = "echo-marker-r01b"


def rejected(crm: Crm, body: Any = None, content: bytes | None = None) -> Any:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    if content is None:
        response = rep.send("POST", CUSTOMERS, json=body)
    else:
        response = rep.send(
            "POST", CUSTOMERS, content=content, headers={"content-type": "application/json"}
        )
    assert response.status_code == 422, response.text[:300]
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert crm.counts() == before
    return response


def errors_of(response: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = response.json()["detail"]
    assert errors, "a 422 with no error"
    for error in errors:
        assert set(error) <= KEYS, error.keys()
        assert {"loc", "msg", "type"} <= set(error), error.keys()
    return errors


def test_r01b_a_body_without_name_is_not_echoed(crm: Crm) -> None:
    body = {"contacts": [{"kind": "email", "value": f"{MARKER}@farm.example.invalid"}]}
    response = rejected(crm, body)
    assert [(e["type"], e["loc"]) for e in errors_of(response)] == [("missing", ["body", "name"])]
    assert MARKER not in response.text


def test_r01b_an_unknown_key_with_a_large_value_is_not_echoed(crm: Crm) -> None:
    body = {"name": "Gospodarstwo", "unknown_key": [MARKER] * 50_000}
    response = rejected(crm, body)
    assert [(e["type"], e["loc"]) for e in errors_of(response)] == [
        ("extra_forbidden", ["body", "unknown_key"])
    ]
    assert MARKER not in response.text
    assert len(response.content) < 1024


def test_r01b_a_literal_error_on_kind_is_not_echoed(crm: Crm) -> None:
    body = {"name": "Gospodarstwo", "contacts": [{"kind": MARKER, "value": "601000001"}]}
    response = rejected(crm, body)
    [error] = errors_of(response)
    assert (error["type"], error["loc"]) == ("literal_error", ["body", "contacts", 0, "kind"])
    assert MARKER not in response.text


def test_r01b_a_body_of_690000_small_objects_without_name_gets_a_small_422(crm: Crm) -> None:
    """No timing bound: the host is shared and loaded. The size and the absence are the claim."""
    content = b'{"x":[' + b",".join([b"{}"] * 690_000) + b"]}"
    assert 1_900_000 < len(content) < 2 * 1024 * 1024
    response = rejected(crm, content=content)
    assert sorted((e["type"], tuple(e["loc"])) for e in errors_of(response)) == [
        ("extra_forbidden", ("body", "x")),
        ("missing", ("body", "name")),
    ]
    assert len(response.content) < 1024, len(response.content)


def test_r01b_contrast_loc_type_and_a_constant_ctx_stay(crm: Crm) -> None:
    response = rejected(crm, {"name": "G", "contacts": [{"kind": "phone", "value": "1"}] * 51})
    [error] = errors_of(response)
    assert (error["type"], error["loc"]) == ("too_long", ["body", "contacts"])
    assert error["ctx"]["max_length"] == 50
    assert all(isinstance(v, int | str) and len(json.dumps(v)) < 200 for v in error["ctx"].values())
