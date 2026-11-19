"""EKO-3-01 fix round 3, R-01 remainder (decision D on Issue #195), through the shipped app on a
real session: the `RequestValidationError` that reaches `_rejected_request` for a body of many
unknown keys holds one error per model, counted by wrapping the application's own handler.
"""

import json
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import Response

from app import main
from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm

pytestmark = pytest.mark.runtime


@pytest.fixture
def reaching(crm: Crm) -> list[int]:
    counts: list[int] = []

    async def counting(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RequestValidationError)
        counts.append(len(exc.errors()))
        return await main._rejected_request(request, exc)

    crm.app.add_exception_handler(RequestValidationError, counting)
    return counts


def send(crm: Crm, body: Any) -> Any:
    rep = crm.login(REP_A, ["rep"])
    before = crm.counts()
    response = rep.send(
        "POST",
        CUSTOMERS,
        content=json.dumps(body, separators=(",", ":")).encode(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text[:300]
    assert crm.counts() == before
    return response


def test_r01c_a_body_of_184000_unknown_keys_reaches_the_handler_as_one_error(
    crm: Crm, reaching: list[int]
) -> None:
    body: dict[str, Any] = {f"k{i}": 0 for i in range(184_000)}
    body["name"] = "Gospodarstwo"
    response = send(crm, body)
    assert reaching == [1]
    [error] = response.json()["detail"]
    assert (error["type"], error["loc"]) == ("extra_forbidden", ["body", "k0"])


def test_r01c_unknown_keys_in_every_contact_reach_the_handler_as_one_error_each(
    crm: Crm, reaching: list[int]
) -> None:
    contacts = [{"kind": "phone", "value": "601000001", **{f"k{i}": 0 for i in range(1_000)}}] * 50
    send(crm, {"name": "Gospodarstwo", "contacts": contacts})
    assert reaching == [50]


def test_r01c_contrast_known_fields_keep_their_per_field_errors(
    crm: Crm, reaching: list[int]
) -> None:
    response = send(crm, {"contacts": [{"kind": "fax", "value": "1"}]})
    assert reaching == [2]
    assert sorted((e["type"], tuple(e["loc"])) for e in response.json()["detail"]) == [
        ("literal_error", ("body", "contacts", 0, "kind")),
        ("missing", ("body", "name")),
    ]
