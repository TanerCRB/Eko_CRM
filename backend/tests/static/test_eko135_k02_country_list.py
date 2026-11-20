"""EKO-1-35 K-02: the frontend's country list and default against the request enum and default of
`CustomerCreate.country` in the document generated at this commit, as sets (D-4, G-D A).

The response's `country` is a plain string on purpose, so only the request enum carries the list.
The frontend files are read as data.
"""

import copy
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tests.support import frontend_contract as fc
from tests.support.api_surface import real_app
from tests.support.contract_tree import copied_tree, run_check

COUNTRIES = "frontend/src/api/countries.ts"
DOMAIN = "backend/app/domain/customers.py"
ISO_COUNT = 249
Document = dict[str, Any]


@cache
def _document() -> Document:
    return real_app().openapi()


def document() -> Document:
    return copy.deepcopy(_document())


def sources() -> dict[str, str]:
    return dict(fc.api_sources())


def planted(old: str, new: str) -> dict[str, str]:
    files = sources()
    assert files[COUNTRIES].count(old) == 1, old
    files[COUNTRIES] = files[COUNTRIES].replace(old, new)
    return files


def country(doc: Document) -> dict[str, Any]:
    found: dict[str, Any] = doc["components"]["schemas"]["CustomerCreate"]["properties"]["country"]
    return found


def swapped_enum(old: str, new: str) -> Callable[[Document], None]:
    def apply(doc: Document) -> None:
        codes = country(doc)["enum"]
        codes[codes.index(old)] = new

    return apply


def judged(files: dict[str, str], *plants: Callable[[Document], None]) -> list[str]:
    doc = document()
    for plant in plants:
        plant(doc)
    return fc.country_findings(files, doc)


def names(problems: list[str], *parts: str) -> bool:
    return any(all(part in line for part in parts) for line in problems)


# The pristine tree and the limit -------------------------------------------------------------


def test_eko135_k02_pristine_tree_agrees() -> None:
    assert fc.country_findings(sources(), document()) == []


def test_eko135_k02_both_sides_hold_249_codes() -> None:
    front, front_default = fc.frontend_countries(sources()[COUNTRIES])
    back, back_default = fc.document_countries(document())
    assert (len(front), len(set(front)), len(back), len(set(back))) == (ISO_COUNT,) * 4
    assert front_default == back_default == "PL"


# One code swapped for a non-ISO pair, on one side alone ---------------------------------------


def test_eko135_k02_frontend_only_swap_fails_naming_the_codes() -> None:
    problems = judged(planted("  ZW\n", "  QQ\n"))
    assert names(problems, COUNTRIES, "QQ") and names(problems, COUNTRIES, "ZW"), problems


def test_eko135_k02_backend_only_swap_fails_on_the_generated_document(tmp_path: Path) -> None:
    tree = copied_tree(tmp_path, {DOMAIN: ("    ZW", "    QQ")})
    result = run_check(tree)
    lines = result.stdout.splitlines()
    assert result.returncode != 0, result.stdout + result.stderr
    assert names(lines, "COUNTRY_CODES", "QQ") and names(lines, "COUNTRY_CODES", "ZW"), lines


def test_eko135_k02_same_swap_on_both_sides_passes(tmp_path: Path) -> None:
    tree = copied_tree(tmp_path, {DOMAIN: ("    ZW", "    QQ"), COUNTRIES: ("  ZW", "  QQ")})
    result = run_check(tree)
    assert (result.returncode, result.stdout) == (0, ""), result.stdout + result.stderr


def test_eko135_k02_document_only_swap_fails_and_both_sides_pass() -> None:
    assert names(judged(sources(), swapped_enum("ZW", "QQ")), "QQ")
    assert judged(planted("  ZW\n", "  QQ\n"), swapped_enum("ZW", "QQ")) == []


def test_eko135_k02_frontend_list_reordered_passes() -> None:
    assert judged(planted("  AD AE AF", "  AF AE AD")) == []


# Edges -----------------------------------------------------------------------------------------


def _without_enum(doc: Document) -> None:
    del country(doc)["enum"]


def _default(value: str) -> Callable[[Document], None]:
    def apply(doc: Document) -> None:
        country(doc)["default"] = value

    return apply


def _response_country_only(doc: Document) -> None:
    del doc["components"]["schemas"]["CustomerCreate"]["properties"]["country"]


EMPTIED = "the codes between the template's backticks"
FULLWIDTH_PL = "ＰＬ"
FAILING: dict[str, tuple[tuple[str, str] | None, Callable[[Document], None] | None, str]] = {
    "frontend-list-emptied": ((EMPTIED, ""), None, "empty"),
    "document-enum-missing": (None, _without_enum, "enum"),
    "document-country-missing": (None, _response_country_only, "country"),
    "one-code-missing": (("  ZW\n", "\n"), None, "ZW"),
    "duplicate-replaces-another": (("  ZW\n", "  ZM\n"), None, "ZM"),
    "lowercase-twin": ((" PL ", " pl "), None, "pl"),
    "fullwidth-twin": ((" PL ", f" {FULLWIDTH_PL} "), None, FULLWIDTH_PL),
    "frontend-default-differs": (
        ('DEFAULT_COUNTRY = "PL"', 'DEFAULT_COUNTRY = "DE"'),
        None,
        "'DE'",
    ),
    "document-default-differs": (None, _default("DE"), "'DE'"),
    "list-not-a-plain-template": (("  ZW\n", "  ${extra}\n"), None, "cannot read"),
    "list-split-otherwise": ((".split(/\\s+/)", ".split(/ /)"), None, "cannot read"),
}


def emptied() -> dict[str, str]:
    files = sources()
    head, rest = files[COUNTRIES].split("export const COUNTRY_CODES = `", 1)
    files[COUNTRIES] = head + "export const COUNTRY_CODES = `" + rest[rest.index("`") :]
    return files


@pytest.mark.parametrize("case_id", sorted(FAILING))
def test_eko135_k02_edge_fails(case_id: str) -> None:
    edit, plant, part = FAILING[case_id]
    if edit is None:
        files = sources()
    else:
        files = emptied() if edit[0] == EMPTIED else planted(*edit)
    problems = judged(files, *([] if plant is None else [plant]))
    assert names(problems, "COUNTRY_CODES", part), (case_id, problems)


def test_eko135_k02_default_changed_on_both_sides_passes() -> None:
    files = planted('DEFAULT_COUNTRY = "PL"', 'DEFAULT_COUNTRY = "DE"')
    assert judged(files, _default("DE")) == []
