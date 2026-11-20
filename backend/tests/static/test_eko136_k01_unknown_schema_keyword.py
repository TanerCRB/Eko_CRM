"""EKO-1-36 (#214) K-01: a schema keyword the contract check neither ignores nor reads fails the
check (EKO-1-35 A-05), with a problem naming the frontend type whose comparison reads the schema
and the keyword, in each place the document reader runs: a component's top level, a property
schema and an `anyOf` member.

Plants go into a copy of the document generated in-process at this commit; the frontend files are
read as data and never edited. Every place holds a `type` and no `$ref`, so the fail-closed branch
of `schema_type` is the only one that can fire (not the reference or the typeless-schema branch).
"""

import copy
from functools import cache
from typing import Any

import pytest

from tests.support import frontend_contract as fc
from tests.support.api_surface import real_app

Document = dict[str, Any]
LABEL = "frontend/src/api/auth.ts: SessionInfo against SessionInfo"
# Where each place sits in the generated document; `holds` is what K-01 requires of it there.
PLACES: dict[str, tuple[tuple[str | int, ...], dict[str, Any]]] = {
    "component": (("SessionInfo",), {"type": "object"}),
    "property": (("SessionInfo", "properties", "subject"), {"type": "string"}),
    "anyof-member": (("SessionInfo", "properties", "name", "anyOf", 0), {"type": "string"}),
}
UNKNOWN: dict[str, Any] = {
    "nullable": True,
    "oneOf": [{"type": "string"}],
    "discriminator": {"propertyName": "kind"},
}


@cache
def _pristine() -> Document:
    return real_app().openapi()


def node_at(document: Document, place: str) -> dict[str, Any]:
    path, holds = PLACES[place]
    node: Any = document["components"]["schemas"]
    for step in path:
        node = node[step]
    assert isinstance(node, dict) and "$ref" not in node, (place, node)
    assert all(node.get(key) == value for key, value in holds.items()), (place, node)
    if place == "component":
        assert "properties" in node, node
    return node


def planted(place: str, keywords: dict[str, Any]) -> Document:
    document = copy.deepcopy(_pristine())
    node_at(document, place).update(keywords)
    return document


def problems(document: Document) -> list[str]:
    return fc.findings(fc.api_sources(), document)


def unread(names: str) -> str:
    """The fail-closed branch's problem for SessionInfo; `names` is the list as it prints."""
    return f"{LABEL}: the check cannot read it (schema keywords the check does not read: {names})"


def test_eko136_k01_the_pristine_document_gives_no_problem() -> None:
    assert problems(copy.deepcopy(_pristine())) == []
    for place in PLACES:
        node_at(copy.deepcopy(_pristine()), place)


@pytest.mark.parametrize("keyword", sorted(UNKNOWN))
@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k01_an_unknown_keyword_fails_naming_the_type_and_the_keyword(
    place: str, keyword: str
) -> None:
    found = problems(planted(place, {keyword: UNKNOWN[keyword]}))
    assert unread(f"['{keyword}']") in found, found


@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k01_contrast_description_in_the_same_place_gives_no_problem(place: str) -> None:
    assert problems(planted(place, {"description": True})) == []


@pytest.mark.parametrize("value", [None, {}, []], ids=["null", "empty-object", "empty-list"])
@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k01_an_empty_value_still_fails_because_the_key_decides(
    place: str, value: Any
) -> None:
    found = problems(planted(place, {"nullable": value}))
    assert unread("['nullable']") in found, found


@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k01_one_unknown_keyword_among_ignored_ones_is_the_only_one_named(
    place: str,
) -> None:
    found = problems(planted(place, {"description": "d", "maxLength": 3, "nullable": True}))
    assert unread("['nullable']") in found, found
    assert not any("maxLength" in problem or "description" in problem for problem in found)


@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k01_two_unknown_keywords_are_both_named_in_sorted_order(place: str) -> None:
    found = problems(planted(place, {"nullable": True, "discriminator": {"propertyName": "k"}}))
    assert unread("['discriminator', 'nullable']") in found, found


@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k01_a_vendor_extension_fails_as_any_other_keyword(place: str) -> None:
    found = problems(planted(place, {"x-order": 1}))
    assert unread("['x-order']") in found, found
