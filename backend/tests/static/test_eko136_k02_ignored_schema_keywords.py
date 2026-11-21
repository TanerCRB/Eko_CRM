"""EKO-1-36 (#214) K-02: each of today's 21 ignored schema keywords, planted in each of K-01's three
places, gives no problem, and the ignored set is exactly those 21 (G-2 A).

The list is written here, not read from `SCHEMA_IGNORED`: iterating over the code's own set would
shrink with it, and a keyword dropped from it would pass in silence.
"""

from typing import Any

import pytest

from tests.static.test_eko136_k01_unknown_schema_keyword import (
    PLACES,
    node_at,
    planted,
    problems,
    unread,
)
from tests.support import frontend_contract as fc

IGNORED = (
    "title",
    "description",
    "default",
    "examples",
    "example",
    "deprecated",
    "format",
    "maxLength",
    "minLength",
    "pattern",
    "maxItems",
    "minItems",
    "uniqueItems",
    "maximum",
    "minimum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "multipleOf",
    "readOnly",
    "writeOnly",
    "additionalProperties",
)
# One changed element each: the case of one letter, or fullwidth look-alike letters.
VARIANTS = ("Description", "maxlength", "ｔｉｔｌｅ")


def test_eko136_k02_the_ignored_set_is_exactly_the_21_keywords() -> None:
    assert len(IGNORED) == 21
    assert len(set(IGNORED)) == 21
    assert fc.SCHEMA_IGNORED == frozenset(IGNORED)


@pytest.mark.parametrize("keyword", IGNORED)
@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k02_each_ignored_keyword_gives_no_problem_in_each_place(
    place: str, keyword: str
) -> None:
    assert problems(planted(place, {keyword: "planted"})) == []


@pytest.mark.parametrize("variant", VARIANTS, ids=["capitalised", "lower-case", "fullwidth"])
@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k02_contrast_a_case_or_look_alike_variant_fails(place: str, variant: str) -> None:
    found = problems(planted(place, {variant: "planted"}))
    assert unread(repr([variant])) in found, found


@pytest.mark.parametrize("value", [None, "", [], {}], ids=["null", "empty", "list", "object"])
@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k02_all_21_at_once_with_an_empty_value_give_no_problem(
    place: str, value: Any
) -> None:
    assert problems(planted(place, dict.fromkeys(IGNORED, value))) == []


@pytest.mark.parametrize("place", sorted(PLACES))
def test_eko136_k02_the_order_of_the_keywords_does_not_matter(place: str) -> None:
    document = planted(place, {})
    node = node_at(document, place)
    original = dict(node)
    node.clear()
    node.update(dict.fromkeys(reversed(IGNORED), "planted"))
    node.update(original)
    assert list(node)[0] == IGNORED[-1]
    assert problems(document) == []
