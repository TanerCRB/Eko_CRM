"""EKO-3-04, ADR-0002-C17 (addendum of EKO-3-04, Q-1 A, Q-2 A): against the pinned PostgreSQL, one
folding rule for the three searched fields whatever their declared collation (ICU `pl-PL` for name
and town, `C` for a contact value), `casefold()` under the builtin `pg_unicode_fast` on both sides;
pattern characters matched literally; and no migration adds an index, an extension or a column
for the search.

The precondition the addendum names (both names present on `postgres:18.6-trixie`) is checked
first, on the same server the carriers use.
"""

import re
import unicodedata

import pytest

from tests.runtime.eko301.conftest import REP_A, Crm
from tests.runtime.eko304.conftest import EMPTY, customer, email, found, search
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

MIGRATIONS = REPO_ROOT / "backend" / "migrations" / "versions"


def test_c17_precondition_casefold_and_pg_unicode_fast_exist(crm: Crm) -> None:
    [(folded, provider)] = crm.pg.rows(
        "SELECT casefold('ŁĄKA ß' COLLATE pg_unicode_fast), "
        "(SELECT collprovider FROM pg_collation WHERE collname = 'pg_unicode_fast')"
    )
    assert (folded, provider) == ("łąka ss", "b")


def test_c17_one_folding_rule_for_name_town_and_a_c_collated_contact_value(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    folded = customer(rep, "ŁĄKOWA", town="ŻÓŁTE", contacts=[email("ŁUKASZ.KOS@example.com")])
    customer(rep, "Inna Farma", town="Wola", contacts=[email("inny@example.com")])
    for query in ("łąk", "żół", "łukasz.kos", unicodedata.normalize("NFD", "ŁĄK")):
        assert found(rep, {"q": query}) == {folded}, query


def test_c17_full_case_folding_not_lower(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    sharp = customer(rep, "Hof Weiß")
    customer(rep, "Hof Schwarz")
    assert found(rep, {"q": "WEISS"}) == {sharp}


def test_c17_pattern_characters_are_literal(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    held = customer(rep, "100% _a\\b")
    customer(rep, "Zwykła Farma")
    for query in ("%", "_", "\\"):
        assert found(rep, {"q": query}) == {held}, query


def test_c17_a_lone_percent_does_not_return_every_customer(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer(rep, "Zwykła Farma")
    customer(rep, "Druga Farma")
    assert search(rep, {"q": "%"}).json() == EMPTY


SEARCH_SCHEMA = re.compile(
    r"pg_trgm|CREATE\s+EXTENSION|create_extension|casefold|_search_key|gin_trgm_ops|"
    r"postgresql_using\s*=\s*[\"']gin",
    re.IGNORECASE,
)


def search_schema_findings(texts: dict[str, str]) -> list[str]:
    return sorted(path for path, text in texts.items() if SEARCH_SCHEMA.search(text))


def test_c17_no_migration_adds_an_index_extension_or_column_for_the_search() -> None:
    texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.py"))}
    assert texts, "no migration read: the check would pass vacuously"
    assert search_schema_findings(texts) == []


@pytest.mark.parametrize(
    "line",
    [
        'op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")',
        'op.create_index("ix", "customer", ["name"], postgresql_using="gin")',
        'op.add_column("customer", sa.Column("name_search_key", sa.Text()))',
    ],
)
def test_c17_contrast_a_planted_search_migration_is_found(line: str) -> None:
    assert search_schema_findings({"0006_planted.py": line}) == ["0006_planted.py"]
