"""EKO-3-01 fix round 3, Reviewer R-01 remainder (decision D on Issue #195): unknown keys are
refused with ONE error per model, before pydantic-core builds one `extra_forbidden` per key, so a
2 MiB body of keys costs one error object, not 184 000. The errors of the known fields are kept,
each with its own `loc`. Counted on the errors validation produces, which is what FastAPI copies
and hands to `_rejected_request`; no timing is measured.

The lone-surrogate fallback of `_rejected_request` is exercised directly with a synthetic error.
"""

import asyncio
import json
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.requests import Request

from app.api.customers import CustomerCreate
from app.main import _rejected_request

PHONE = {"kind": "phone", "value": "601000001"}


def errors_of(body: Any) -> list[dict[str, Any]]:
    with pytest.raises(ValidationError) as rejected:
        CustomerCreate.model_validate(body)
    return [dict(error) for error in rejected.value.errors(include_url=False)]


def kinds(errors: list[dict[str, Any]]) -> list[tuple[str, tuple[Any, ...]]]:
    return [(e["type"], tuple(e["loc"])) for e in errors]


def test_r01c_many_unknown_top_level_keys_give_one_error() -> None:
    body: dict[str, Any] = {"name": "Gospodarstwo", **{f"k{i}": 0 for i in range(184_000)}}
    assert kinds(errors_of(body)) == [("extra_forbidden", ("k0",))]


def test_r01c_many_unknown_keys_inside_one_contact_give_one_error() -> None:
    contact = {**PHONE, **{f"k{i}": 0 for i in range(10_000)}}
    body = {"name": "Gospodarstwo", "contacts": [contact]}
    assert kinds(errors_of(body)) == [("extra_forbidden", ("contacts", 0, "k0"))]


def test_r01c_unknown_keys_in_several_contacts_give_one_error_per_contact() -> None:
    contacts = [{**PHONE, **{f"k{i}": 0 for i in range(2_000)}} for _ in range(50)]
    errors = errors_of({"name": "Gospodarstwo", "contacts": contacts})
    assert kinds(errors) == [("extra_forbidden", ("contacts", n, "k0")) for n in range(50)]


def test_r01c_unknown_keys_and_invalid_known_fields_keep_the_known_fields_errors() -> None:
    body = {"contacts": [{"kind": "fax", "value": "1"}], **{f"k{i}": 0 for i in range(1_000)}}
    assert sorted(kinds(errors_of(body))) == [
        ("extra_forbidden", ("k0",)),
        ("literal_error", ("contacts", 0, "kind")),
        ("missing", ("name",)),
    ]


def test_r01c_contrast_known_fields_only_get_their_per_field_errors() -> None:
    body = {"contacts": [{"kind": "fax", "value": "1"}]}
    assert sorted(kinds(errors_of(body))) == [
        ("literal_error", ("contacts", 0, "kind")),
        ("missing", ("name",)),
    ]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param([1], [("model_type", ())], id="list"),
        pytest.param("x", [("model_type", ())], id="string"),
        pytest.param({"name": "G", "contacts": [5]}, [("model_type", ("contacts", 0))], id="item"),
    ],
)
def test_r01c_a_non_dict_input_gets_the_same_error_as_before(
    body: Any, expected: list[tuple[str, tuple[Any, ...]]]
) -> None:
    assert kinds(errors_of(body)) == expected


def test_r01c_a_lone_surrogate_key_is_one_string_unicode_error_as_before() -> None:
    body = {"name": "G", **{f"k{i}": 0 for i in range(1_000)}, "\ud800": 1}
    assert kinds(errors_of(body)) == [("string_unicode", ())]


def test_r01c_the_surrogate_fallback_answers_422_escaped_not_500() -> None:
    """A guard against a library change: no current model puts a lone surrogate in `loc`."""
    exc = RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": ("body", "\ud800"),
                "msg": "Extra inputs are not permitted",
            }
        ]
    )
    request = Request({"type": "http", "method": "POST", "path": "/api/customers", "headers": []})
    response = asyncio.run(_rejected_request(request, exc))
    assert response.status_code == 422
    body = bytes(response.body)
    assert body.isascii()
    assert json.loads(body) == {
        "detail": [
            {
                "type": "extra_forbidden",
                "loc": ["body", "\ud800"],
                "msg": "Extra inputs are not permitted",
            }
        ]
    }
