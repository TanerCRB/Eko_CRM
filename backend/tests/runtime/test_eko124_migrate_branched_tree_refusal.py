"""EKO-1-24 K-01: migrate refuses a branched revision tree naming both heads.

On a variant image FROM the shipped image adding the two sibling revisions (the proven add-only
variant mechanism), migrate exits non-zero, applies nothing, and its refusal line starts with
"migrate refused:" and names both head revisions instead of reading "unknown destination
revision". The contrast builds the variant with only one sibling: the run applies it, so the
second head — not the image or the database — caused the refusal. The before-connection order,
the three-head generalization (edge (a)) and the exact contrast texts are carried on the unit
surface (`tests/unit/test_eko124_migrate_branched_tree_refusal.py`).
"""

import pytest

from tests.runtime.lab import Lab, configuration_values
from tests.support.log_lines import leaks
from tests.support.migration_checks import leaked_values

pytestmark = pytest.mark.runtime

TWO_HEADS = ("t_sibling_a.py", "t_sibling_b.py")


def refusal_line(logs: str) -> str:
    """The plain-text line the SystemExit message writes, matched at the line start."""
    lines = [line for line in logs.splitlines() if line.startswith("migrate refused:")]
    assert lines, logs[-2000:]
    [line] = lines
    return line


def assert_names_both_heads(logs: str) -> str:
    line = refusal_line(logs)
    assert "t_sibling_a" in line, line
    assert "t_sibling_b" in line, line
    assert "unknown destination revision" not in line, line
    return line


def test_eko124_k01_branched_tree_refusal_names_both_heads(lab: Lab) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(lab.variant("two_heads", files=TWO_HEADS))
    assert code != 0, logs
    assert_names_both_heads(logs)
    assert lab.comparison_dump() == before


def test_eko124_k01_contrast_single_sibling_variant_applies(lab: Lab) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(lab.variant("sibling_a"))
    assert code == 0, logs
    assert lab.versions() == ["t_sibling_a"]
    assert lab.comparison_dump() != before


def test_eko124_k01_edge_empty_database_refuses_and_creates_nothing(lab: Lab) -> None:
    lab.reset()
    code, logs = lab.run_migrate(lab.variant("two_heads", files=TWO_HEADS))
    assert code != 0, logs
    assert_names_both_heads(logs)
    assert lab.versions() is None
    assert lab.lineage() is None


def test_eko124_k01_edge_no_configuration_value_in_the_refusal_or_the_log(lab: Lab) -> None:
    lab.at_head()
    code, logs = lab.run_migrate(lab.variant("two_heads", files=TWO_HEADS))
    assert code != 0, logs
    values = configuration_values(lab)
    assert leaked_values(refusal_line(logs), values) == []
    assert leaks(logs, *values) == []
