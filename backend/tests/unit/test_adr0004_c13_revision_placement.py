"""K-02, K-03: the descent rules of the ADR-0004 addendum of 2026-10-29, as one function of `data`.

The runtime tests prove the rules in the containers; these name every row of the rules table and
check that the code's tree is read the way Alembic reads it.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.data.schema_revision import (
    DatabaseRevision,
    Placement,
    RevisionRefused,
    RevisionTree,
    check_migratable,
    check_servable,
    code_tree,
    place,
    tree_from_files,
)
from tests.support.repo import REPO_ROOT

SHIPPED = RevisionTree(("0001", "0002"))
NEXT = RevisionTree(("0001", "0002", "t_next"))
REVISIONS = Path(__file__).parents[1] / "runtime" / "revisions"
VERSIONS = REPO_ROOT / "backend" / "migrations" / "versions"
FULL_LINEAGE = frozenset({"0001", "0002", "t_next"})

# (alembic_version rows or None for no table, lineage rows or None for no table, tree) -> placement
CASES = {
    "no alembic_version table": (None, None, SHIPPED, Placement.EMPTY),
    "no row": ((), frozenset({"0001", "0002"}), SHIPPED, Placement.NO_ROW),
    "two rows": (("0001", "0002"), frozenset({"0001", "0002"}), SHIPPED, Placement.SEVERAL_ROWS),
    "head": (("0002",), frozenset({"0001", "0002"}), SHIPPED, Placement.HEAD),
    "head without lineage": (("0002",), None, SHIPPED, Placement.HEAD),
    "ancestor": (("0001",), None, SHIPPED, Placement.ANCESTOR),
    "descendant": (("t_next",), FULL_LINEAGE, SHIPPED, Placement.DESCENDANT),
    "descendant, lineage dropped": (("t_next",), None, SHIPPED, Placement.UNPLACEABLE),
    "descendant, lineage emptied": (("t_next",), frozenset(), SHIPPED, Placement.UNPLACEABLE),
    "unknown identifier": (("zz",), frozenset({"0001", "0002"}), SHIPPED, Placement.UNPLACEABLE),
    "lineage lacks the code's head": (
        ("t_b",),
        frozenset({"0001", "t_b"}),
        SHIPPED,
        Placement.UNPLACEABLE,
    ),
    "sibling": (
        ("t_b",),
        frozenset({"0001", "0002", "t_b"}),
        RevisionTree(("0001", "0002", "t_a")),
        Placement.UNPLACEABLE,
    ),
    "the next release at its own head": (("t_next",), FULL_LINEAGE, NEXT, Placement.HEAD),
}
SERVED = {Placement.HEAD, Placement.DESCENDANT}


@pytest.mark.parametrize("case", sorted(CASES))
def test_adr0004_c13_placement_follows_the_rules_table(case: str) -> None:
    versions, lineage, tree, expected = CASES[case]
    assert place(DatabaseRevision(versions, lineage), tree) is expected


@pytest.mark.parametrize("case", sorted(CASES))
def test_adr0004_c13_backend_and_worker_serve_only_head_and_a_descendant(case: str) -> None:
    versions, lineage, tree, expected = CASES[case]
    database = DatabaseRevision(versions, lineage)
    if expected in SERVED:
        check_servable(database, tree)
    else:
        with pytest.raises(RevisionRefused):
            check_servable(database, tree)


@pytest.mark.parametrize("case", sorted(CASES))
def test_adr0004_c13_migrate_upgrades_empty_and_ancestor_and_fails_the_unplaceable(
    case: str,
) -> None:
    versions, lineage, tree, expected = CASES[case]
    database = DatabaseRevision(versions, lineage)
    if expected in {Placement.EMPTY, Placement.ANCESTOR}:
        assert check_migratable(database, tree) is True
    elif expected in SERVED:
        assert check_migratable(database, tree) is False
    else:
        with pytest.raises(RevisionRefused):
            check_migratable(database, tree)


def test_adr0004_c13_refusal_names_the_revisions_and_the_reason() -> None:
    with pytest.raises(RevisionRefused) as refused:
        check_servable(DatabaseRevision(("0001",), None), SHIPPED)
    assert "0001" in str(refused.value)
    assert "0002" in str(refused.value)
    assert "older" in str(refused.value)


def alembic_lineage(versions: Path) -> tuple[str, ...]:
    config = Config()
    config.set_main_option("script_location", str(versions.parent))
    config.set_main_option("path_separator", "os")
    config.set_main_option("version_locations", str(versions))
    script = ScriptDirectory.from_config(config)
    [head] = script.get_heads()
    return tuple(reversed([r.revision for r in script.iterate_revisions(head, "base")]))


def test_adr0004_c13_code_tree_is_the_shipped_tree_as_alembic_reads_it() -> None:
    assert code_tree() == RevisionTree(alembic_lineage(VERSIONS))
    assert code_tree() == SHIPPED


def test_adr0004_c13_tree_from_files_reads_an_added_revision(tmp_path: Path) -> None:
    for path in VERSIONS.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "t_next.py").write_bytes((REVISIONS / "t_next.py").read_bytes())
    assert tree_from_files(tmp_path) == NEXT
    assert tree_from_files(tmp_path) == RevisionTree(alembic_lineage(tmp_path))


def test_adr0004_c13_tree_from_files_refuses_two_heads(tmp_path: Path) -> None:
    for path in VERSIONS.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    for name in ("t_sibling_a.py", "t_sibling_b.py"):
        (tmp_path / name).write_bytes((REVISIONS / name).read_bytes())
    with pytest.raises(RevisionRefused):
        tree_from_files(tmp_path)


def test_adr0004_c13_tree_from_files_refuses_a_file_without_a_revision(tmp_path: Path) -> None:
    for path in VERSIONS.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "stray.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(RevisionRefused):
        tree_from_files(tmp_path)
