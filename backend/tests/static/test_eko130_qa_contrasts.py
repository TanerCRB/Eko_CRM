"""EKO-1-30 QA contrasts: the red side of the retune-simulation guards, in-tree.

The eko130 simulation's claims are wiring claims, and at rest every mechanism they guard is
green — a check that can only pass proves nothing. Each node here drives the *actual* eko130
node callable against an input with exactly one element changed and the verdict reversed:

- the wiring node against a source where the record bound is an alias of the live bound, and
  against a source where k02 imports the live constants back (the two M-1 forms — the twins
  are both 360, so no value comparison can see the difference; CPython even interns the two
  module-level `360` literals into one object, so no identity comparison can either);
- the overclaim grep against a source carrying the pre-fix byte-equality sentence (M-4'),
  in both grammars the grep forbids: the literal `same bytes`, and any sentence pairing a
  byte-word with the comment;
- the bare-death classifier against a real bare death — a plant `job_edit` built on a line
  constant desynced from the recorded value (the M-2 failure mode, R-01's 13 bare deaths) —
  contrasted with an ordinary verdict assertion of the same exception type;
- the record-pinning node against a moved recorded value and a moved record SHA (M-5/M-6b's
  in-tree surface);
- the paired-application node against a `_masked` whose expected line no longer derives from
  the bound it is given (M-7b: a module literal, statically equal at rest, so only the
  simulated move can see it).

Nothing here edits a guard file or the repository: the mutated readings are monkeypatched
`_source` results and module attributes, undone after each node. The on-disk mutations that
these contrasts mirror were run and recorded in the QA report for this task.
"""

from pathlib import Path
from types import ModuleType

import pytest

from tests.static import test_eko127_k01_release_runtime_bound_is_the_recorded_value as k01
from tests.static import test_eko127_k02_release_yml_changes_only_the_runtime_bound as k02
from tests.static import test_eko130_retune_simulation_separates_live_from_record as sim
from tests.static.test_eko125_k04_runtime_collection_unchanged import job_edit
from tests.support.fixed_pair import Throwaway

pytestmark = pytest.mark.usefixtures("real_repository_untouched")


def _patched_source(
    monkeypatch: pytest.MonkeyPatch, target: ModuleType, old: str, new: str
) -> None:
    """Serve `target`'s source with exactly one replacement; every other module unchanged."""
    original = sim._source

    def patched(module: ModuleType) -> str:
        text = original(module)
        if module is target:
            assert text.count(old) == 1, f"anchor {old!r} is not unique in {module.__name__}"
            return text.replace(old, new)
        return text

    monkeypatch.setattr(sim, "_source", patched)


def test_eko130_qa_the_wiring_node_rejects_both_forms_of_collapsing_the_separation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-1's red side, both forms, through the real wiring node: aliasing the record bound to
    the live one, and pointing k02's from-import back at the live names. Unmutated, the same
    node passes — one element changed (the wiring), verdict reversed."""
    sim.test_eko130_k01_the_separation_is_by_wiring_not_by_value()

    _patched_source(monkeypatch, k01, "RECORDED_BOUND = 360", "RECORDED_BOUND = BOUND")
    with pytest.raises(AssertionError, match="not an alias"):
        sim.test_eko130_k01_the_separation_is_by_wiring_not_by_value()
    monkeypatch.undo()

    _patched_source(
        monkeypatch,
        k02,
        "    RECORDED_BOUND,\n    RECORDED_BOUND_LINE,\n",
        "    BOUND as RECORDED_BOUND,\n    BOUND_LINE as RECORDED_BOUND_LINE,\n",
    )
    with pytest.raises(AssertionError, match="imports live constants"):
        sim.test_eko130_k01_the_separation_is_by_wiring_not_by_value()
    monkeypatch.undo()

    sim.test_eko130_k01_the_separation_is_by_wiring_not_by_value()


def test_eko130_qa_the_overclaim_grep_rejects_a_reinserted_byte_equality_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-4's red side, in both grammars the grep node forbids: the literal pre-fix sentence
    (`same bytes`), and a differently-worded claim that pairs a byte-word with the comment.
    Unmutated, the same node passes."""
    sim.test_eko130_k03_the_raise_annotation_does_not_overclaim_the_comment()
    anchor = "never for content."

    _patched_source(
        monkeypatch,
        k01,
        anchor,
        anchor + " The claim node then requires the head to carry the same bytes.",
    )
    with pytest.raises(AssertionError, match="same bytes"):
        sim.test_eko130_k03_the_raise_annotation_does_not_overclaim_the_comment()
    monkeypatch.undo()

    _patched_source(
        monkeypatch,
        k01,
        anchor,
        anchor + " The provenance comment is compared byte for byte.",
    )
    with pytest.raises(AssertionError, match="byte for byte"):
        sim.test_eko130_k03_the_raise_annotation_does_not_overclaim_the_comment()
    monkeypatch.undo()

    sim.test_eko130_k03_the_raise_annotation_does_not_overclaim_the_comment()


def test_eko130_qa_the_bare_death_classifier_separates_a_verdict_from_plant_machinery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The K-01b detector's red side: at rest no driven node dies bare, so a classifier that
    always answered "not bare" would pass the whole suite. Driven through the simulation's own
    `_verdict`, the same exception type classifies by where it is raised — a body-level verdict
    assertion is `red`, and an assertion raised inside plant machinery is `bare`. The bare
    side is R-01's failure mode rebuilt with one element: a `job_edit` whose old line does not
    derive from the recorded value (361 where the pinned head carries 360), exactly what an
    independent `RECORDED_BOUND_LINE` literal produces (M-2)."""

    def test_eko130_qa_synthetic_verdict_death() -> None:
        value = 361
        assert value == 360, "synthetic verdict death"

    def test_eko130_qa_synthetic_bare_death(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = Throwaway(tmp_path / "repo", k01.HEAD, monkeypatch)
        desynced = job_edit(k01.RELEASE, k01.RUNTIME, f"    {k01.TIMEOUT}: 361\n", "")
        repo.commit(k01.HEAD, desynced)

    monkeypatch.setattr(
        k02,
        test_eko130_qa_synthetic_verdict_death.__name__,
        test_eko130_qa_synthetic_verdict_death,
        raising=False,
    )
    monkeypatch.setattr(
        k02,
        test_eko130_qa_synthetic_bare_death.__name__,
        test_eko130_qa_synthetic_bare_death,
        raising=False,
    )

    state, note = sim._verdict(
        k02, test_eko130_qa_synthetic_verdict_death.__name__, tmp_path / "v", monkeypatch, False
    )
    assert state == "red", (state, note)
    assert "verdict assertion" in note, note

    state, note = sim._verdict(
        k02, test_eko130_qa_synthetic_bare_death.__name__, tmp_path / "b", monkeypatch, False
    )
    assert state == "bare", (state, note)
    assert note.endswith(":change"), note


def test_eko130_qa_the_record_pinning_node_rejects_a_moved_value_or_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The K-04 in-tree node's red side: a recorded bound moved to 361 (M-5's element) or a
    record SHA moved (M-6b's element) reddens it; untouched, it passes."""
    pinned = sim.test_eko130_k04_the_record_values_and_plant_names_are_pinned
    pinned()

    monkeypatch.setattr(k01, "RECORDED_BOUND", 361)
    with pytest.raises(AssertionError):
        pinned()
    monkeypatch.undo()

    monkeypatch.setattr(k01, "BASE", "0" * 40)
    with pytest.raises(AssertionError):
        pinned()
    monkeypatch.undo()

    pinned()


def _neutral_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The simulation driver's own recipe (`_verdict`): each driven node starts from a neutral
    environment — a previous node's `Throwaway.select` leaves GIT_DIR/GIT_WORK_TREE pointing
    into a throwaway, which would poison the next `Throwaway.__init__`'s object-store lookup."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "CHANGESET_BASE"):
        monkeypatch.delenv(name, raising=False)


def test_eko130_qa_the_paired_application_node_rejects_a_frozen_expected_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-7b's red side: `_masked`'s expected line frozen to the record literal — statically
    indistinguishable at rest (both read 360), so only the simulated paired move can see it.
    With the derivation replaced by a constant function, the real K-05 node reddens on its
    first assert (the moved pair no longer passes); with the derivation restored, it passes."""
    paired = sim.test_eko130_k05_the_simulated_move_carries_the_line_and_raise_with_the_value
    _neutral_env(monkeypatch)
    paired(tmp_path / "green", monkeypatch)

    def frozen(bound: int) -> str:
        return k01.bound_line_of(k01.RECORDED_BOUND)

    monkeypatch.setattr(k02, "bound_line_of", frozen)
    _neutral_env(monkeypatch)
    with pytest.raises(AssertionError):
        paired(tmp_path / "frozen", monkeypatch)
    monkeypatch.undo()

    _neutral_env(monkeypatch)
    paired(tmp_path / "restored", monkeypatch)
