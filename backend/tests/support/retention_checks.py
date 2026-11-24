"""ADR-0005-C20 (ADR-0005 addendum of EKO-3-08, Q-3 A): a column holding a staff subject is named
`*_subject`, and every such column of the application schema is in the retention's reference set.
Each check returns what it finds, so a planted schema shows it failing.
"""

from collections.abc import Iterable

from sqlalchemy import MetaData

SUBJECT_SUFFIX = "_subject"


def column_names(columns: Iterable[object]) -> frozenset[str]:
    """`table.column` for each mapped column of the reference set."""
    named = set()
    for column in columns:
        table = getattr(column, "table", None)
        named.add(f"{getattr(table, 'name', '?')}.{getattr(column, 'name', '?')}")
    return frozenset(named)


def subject_columns(metadata: MetaData) -> set[str]:
    return {
        f"{table.name}.{column.name}"
        for table in metadata.tables.values()
        for column in table.columns
        if column.name.endswith(SUBJECT_SUFFIX)
    }


def missing_from_reference_set(metadata: MetaData, reference: Iterable[object]) -> list[str]:
    """Every `*_subject` column of the schema that the reference set does not hold."""
    return sorted(subject_columns(metadata) - column_names(reference))
