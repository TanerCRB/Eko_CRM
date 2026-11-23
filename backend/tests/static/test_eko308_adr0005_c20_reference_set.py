"""EKO-3-08, ADR-0005-C20 (ADR-0005 addendum of EKO-3-08, Q-3 A), static half: every column of the
application schema whose name ends in `_subject` is in the retention's reference set held in the
code, and that set equals the list held here. A planted `_subject` column outside the set fails.
The behavioural half (a copy referred to by each column of the set is kept past 180 days) is
`tests/runtime/eko308/test_eko308_k05_display_name_retention.py`.
"""

from sqlalchemy import Column, MetaData, Table, Text

from app.data.models import Base
from app.data.staff import REFERENCE_SET
from tests.support import retention_checks as rc

# Adding a column is the release that adds it, named at its gate 1 (ADR-0005 addendum of EKO-3-08).
HELD = frozenset({"customer.owner_subject"})


def test_c20_the_code_reference_set_is_the_set_held_here() -> None:
    assert rc.column_names(REFERENCE_SET) == HELD


def test_c20_every_subject_column_of_the_schema_is_in_the_reference_set() -> None:
    found = rc.subject_columns(Base.metadata)
    # Non-vacuity: the one referring column of this date is found by the naming rule.
    assert "customer.owner_subject" in found
    assert rc.missing_from_reference_set(Base.metadata, REFERENCE_SET) == []


def test_c20_contrast_a_planted_subject_column_outside_the_set_fails() -> None:
    planted = MetaData()
    Table("customer", planted, Column("owner_subject", Text))
    Table("visit", planted, Column("author_subject", Text), Column("subject", Text))
    assert rc.missing_from_reference_set(planted, REFERENCE_SET) == ["visit.author_subject"]


def test_c20_contrast_a_column_named_subject_alone_is_not_a_referring_column() -> None:
    planted = MetaData()
    Table("app_session", planted, Column("subject", Text))
    assert rc.subject_columns(planted) == set()
