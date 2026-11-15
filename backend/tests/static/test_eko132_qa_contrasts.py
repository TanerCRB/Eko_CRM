"""EKO-1-32 QA contrasts: the red side of this task's new guards, in-tree.

The labeled on-disk mutations (EKO-1-32/M-1..M-8) are QA runs recorded in the task's QA
report and PR; each node here mirrors one of them through the *real* guard callable with
exactly one element changed and the verdict reversed, so the red side outlives the run
(house pattern: test_eko130_qa_contrasts.py):

- the disk-glob node (K-02) against an undeclared probe stem and against a declared module
  missing from disk — the M-3 forms, through a monkeypatched `_static_dir` (the real disk
  is never written to here; the labeled M-3 run plants the probe file itself);
- the requiredness node (K-03) against a restored `= BOUND` default — the M-4b form,
  behavior-inert while the twins are both 360, which is why the assertion is the tooth;
- the call-site scan (K-04) against both R-02 forms at the k01 record site — naming the
  live `BOUND` (M-5) and dropping the argument (M-4's static surface) — through the house
  patched-source recipe (monkeypatched `sim._source`, undone after each phase);
- the wiring node (K-05) against `RECORDED_RAISE = raise_for(BOUND)` — the M-6 form,
  EKO-1-30's ninth paper mutation, here as a permanent in-tree mirror;
- the agreement mechanism (K-07) against a de-parameterized live node — the M-8 form: the
  node stays green under the simulated bound, and `_agreement` names the green-but-move
  mismatch that reddens the simulated driving node under the labeled run.

Nothing here edits a guard file or the repository: the mutated readings are monkeypatched
attributes and `sim._source` results, undone after each phase.
"""

from pathlib import Path
from types import ModuleType

import pytest

from tests.static import test_eko127_k01_release_runtime_bound_is_the_recorded_value as k01
from tests.static import test_eko130_retune_simulation_separates_live_from_record as sim
from tests.static import test_eko132_coverage_bound_pair as cov

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# the scan's single exclusion, reused from the delivered module (never a second literal)
LIVE_ID = cov.LIVE_NODE


def _patched_k01(monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    """Serve k01's source through `sim._source` with exactly one replacement (the house
    `_patched_source` recipe of test_eko130_qa_contrasts.py, specialized to k01)."""
    original = sim._source

    def patched(module: ModuleType) -> str:
        text = original(module)
        if module is k01:
            assert text.count(old) == 1, f"anchor {old!r} is not unique in k01"
            return text.replace(old, new)
        return text

    monkeypatch.setattr(sim, "_source", patched)


def test_eko132_qa_the_disk_glob_node_rejects_an_undeclared_or_missing_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-3's red side without touching the real disk: the declaration node reddens on one
    extra undeclared stem, and on one declared stem missing from disk; unmutated it passes.
    One element per phase, verdict reversed each time."""
    declaration = cov.test_eko132_k02_the_modules_declaration_covers_every_eko127_file_on_disk
    declaration()

    def fake_dir(name: str, stems: list[str]) -> Path:
        directory = tmp_path / name
        directory.mkdir()
        for stem in stems:
            (directory / f"{stem}.py").touch()
        return directory

    declared = [module.__name__.rpartition(".")[2] for module in sim.MODULES]
    with_probe = [*declared, "test_eko127_k99_probe"]
    monkeypatch.setattr(cov, "_static_dir", lambda: fake_dir("extra", with_probe))
    with pytest.raises(AssertionError, match="test_eko127_k99_probe"):
        declaration()
    monkeypatch.undo()

    monkeypatch.setattr(cov, "_static_dir", lambda: fake_dir("missing", declared[:-1]))
    with pytest.raises(AssertionError, match="declared but not on disk"):
        declaration()
    monkeypatch.undo()

    declaration()


def test_eko132_qa_the_requiredness_node_rejects_a_restored_live_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-4b's red side: restoring the pre-task `bound: int = BOUND` default on the helper is
    behavior-inert while the twins are both 360 — the requiredness assertion is the only
    mechanism that can see it, and it reddens; restored, it passes again."""
    required = cov.test_eko132_k03_the_bound_argument_of_bound_violations_is_required
    required()

    original = k01.bound_violations

    def defaulted(text: str, bound: int = k01.BOUND) -> list[str]:
        return original(text, bound)

    monkeypatch.setattr(k01, "bound_violations", defaulted)
    with pytest.raises(AssertionError, match="defaults bound to 360"):
        required()
    monkeypatch.undo()

    required()


def test_eko132_qa_the_call_site_scan_rejects_a_live_alias_and_a_dropped_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-5's and M-4's static red sides through the real scan node: one token at the k01
    record site (`RECORDED_BOUND` to `BOUND`), or the argument dropped entirely. Both forms
    keep every value-driven node green while the twins are 360 (R-02's named failure mode);
    the scan names the site in both cases."""
    scan = cov.test_eko132_k04_no_record_call_site_reads_the_live_pair
    scan()

    site = "assert bound_violations(pinned_text(HEAD), RECORDED_BOUND) == []"
    _patched_k01(monkeypatch, site, "assert bound_violations(pinned_text(HEAD), BOUND) == []")
    with pytest.raises(AssertionError, match="passes BOUND"):
        scan()
    monkeypatch.undo()

    _patched_k01(monkeypatch, site, "assert bound_violations(pinned_text(HEAD)) == []")
    with pytest.raises(AssertionError, match="drops its bound argument"):
        scan()
    monkeypatch.undo()

    scan()


def test_eko132_qa_the_wiring_node_rejects_the_raise_rewired_to_the_live_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-6's red side — EKO-1-30's ninth paper mutation as a permanent in-tree mirror:
    `RECORDED_RAISE = raise_for(BOUND)` is value-invisible while the twins are both 360; the
    wiring node's `_helper_call` shape check is the sole tooth and it reddens."""
    wiring = sim.test_eko130_k01_the_separation_is_by_wiring_not_by_value
    wiring()

    _patched_k01(
        monkeypatch,
        "RECORDED_RAISE = raise_for(RECORDED_BOUND)",
        "RECORDED_RAISE = raise_for(BOUND)",
    )
    with pytest.raises(AssertionError, match=r"must be raise_for\(RECORDED_BOUND\)"):
        wiring()
    monkeypatch.undo()

    wiring()


def test_eko132_qa_the_agreement_rejects_a_live_node_deparameterized_to_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-8's red side, driven through the real `_verdict`/`_agreement` chain: with the
    signature parameterization dropped and the body hardcoding `BOUND`, the live node stays
    green under the simulated bound — and the agreement names it as the green-but-move
    mismatch, which is what reddens the simulated driving node under the labeled run.
    Restored, the same node reddens under the simulated bound again."""
    state, note = sim._verdict(k01, LIVE_ID, tmp_path / "real", monkeypatch, simulated=True)
    assert state == "red" and "verdict assertion" in note, (state, note)

    def hardcoded() -> None:
        assert k01.bound_violations(k01.live_text(), k01.BOUND) == []

    monkeypatch.setattr(k01, LIVE_ID, hardcoded)
    state, note = sim._verdict(k01, LIVE_ID, tmp_path / "mutated", monkeypatch, simulated=True)
    assert state == "green", (state, note)
    problems = sim._agreement(set(), sim.classification())
    assert any(
        LIVE_ID in problem and "green under the simulated bound" in problem for problem in problems
    ), problems
    monkeypatch.undo()

    state, note = sim._verdict(k01, LIVE_ID, tmp_path / "restored", monkeypatch, simulated=True)
    assert state == "red", (state, note)
