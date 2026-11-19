"""EKO-3-01 fix round 3, QA contrasts for `RequestModel` (decision D on Issue #195).

- The key named is the first unknown key in body order, not the first sorted, and not the last.
  The keys here are not in alphabetical order, so a sorted scan names a different one.
- The same rule holds inside a contact: one error naming that contact's first unknown key.
- A lone-surrogate key inside a contact gives one `string_unicode` at that contact.
- A lone-surrogate key after an ordinary unknown key still gives `string_unicode`, not an
  `extra_forbidden` naming the earlier key: every unknown key is scanned, not just the named one.
- Unknown keys never hide a known field's error, and a known field's error never hides the unknown
  key: both are named, each once.

Every value is synthetic (ADR-0005).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.api.customers import CustomerCreate

PHONE = {"kind": "phone", "value": "601000001"}


def kinds(body: Any) -> list[tuple[str, tuple[Any, ...]]]:
    with pytest.raises(ValidationError) as rejected:
        CustomerCreate.model_validate(body)
    return [(e["type"], tuple(e["loc"])) for e in rejected.value.errors(include_url=False)]


def test_qa_r01c_the_first_unknown_key_in_body_order_is_named() -> None:
    body = {"zeta": 1, "name": "Gospodarstwo", "mid": 1, "alpha": 1}
    assert kinds(body) == [("extra_forbidden", ("zeta",))]


def test_qa_r01c_contrast_the_same_keys_in_another_order_name_another_key() -> None:
    body = {"alpha": 1, "name": "Gospodarstwo", "mid": 1, "zeta": 1}
    assert kinds(body) == [("extra_forbidden", ("alpha",))]


def test_qa_r01c_inside_a_contact_the_first_unknown_key_is_named() -> None:
    contact = {**PHONE, "zz": 1, "aa": 2}
    body = {"name": "Gospodarstwo", "contacts": [contact]}
    assert kinds(body) == [("extra_forbidden", ("contacts", 0, "zz"))]


def test_qa_r01c_a_lone_surrogate_key_inside_a_contact_is_string_unicode() -> None:
    contact = {**PHONE, "zz": 1, "\ud800": 1}
    body = {"name": "Gospodarstwo", "contacts": [contact]}
    assert kinds(body) == [("string_unicode", ("contacts", 0))]


def test_qa_r01c_a_lone_surrogate_after_an_unknown_key_is_still_string_unicode() -> None:
    body = {"name": "Gospodarstwo", "first": 1, "\ud800": 1}
    assert kinds(body) == [("string_unicode", ())]


def test_qa_r01c_an_unknown_key_and_a_known_error_are_both_named_once() -> None:
    body = {"name": "", "unknown": 1, "other": 2}
    assert sorted(kinds(body)) == [("extra_forbidden", ("unknown",)), ("value_error", ("name",))]


def test_qa_r01c_contrast_a_valid_body_with_one_unknown_key_names_only_the_key() -> None:
    body = {"name": "Gospodarstwo", "unknown": 1}
    assert kinds(body) == [("extra_forbidden", ("unknown",))]
