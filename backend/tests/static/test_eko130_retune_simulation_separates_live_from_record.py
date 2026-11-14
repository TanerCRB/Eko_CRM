"""EKO-1-30 (#152): a simulated retune moves the live bound and reddens only the classified
must-move nodes — the record of #138 stays pinned and inert.

R-01's failure mode: `test_eko127_k01_*`'s `BOUND`/`BOUND_LINE` were imported by the
pair-frozen k02/k03, so a future retune (EKO-1-27's DoD: "a duration reaching the bound
returns the value to gate 1") would redden record history — ~6 assertion-red nodes and 13
plant nodes dying with a bare `AssertionError` from `job_edit`/`_bound_dropped`, readable as
a broken guard rather than as history that must not move. This test drives the *actual*
eko127 node callables (Q-A A, gate 1 of #152: the violation functions are parameterized by
the bound, the module constants are the defaults at their call sites; no monkeypatching —
fact 7: from-imports bind at import time, a patch of a module attribute does not reach the
importers) at a `SIMULATED_BOUND` different from the recorded 360 and asserts three things:

- every eko127 node green at rest (the recorded baseline — today's suite, one element:
  the bound, unchanged);
- under the simulated move the red set equals exactly the must-move classification of
  k01's docstring (Q-B A: machine-readable, agreement enforced node for node here);
- no driven node dies with a bare `AssertionError` raised inside plant machinery rather
  than by its own verdict — the 13-node failure mode caught in-tree.

The paired application (K-05): a retune moves value, bound line and RAISE text together;
this test applies the simulated bound through the pair helpers (`bound_line_of`,
`raise_for`), never by writing a line text of its own — a literalized line constant left
behind by a moved value is what the 18-red scenario was, and it must redden this test.
Nothing here edits `.github/workflows/release.yml` or the real repository (K-04): the
simulated heads live in a `Throwaway`; `real_repository_untouched` is the module guard.
"""

import ast
import inspect
import re
import traceback
from pathlib import Path
from types import ModuleType

import pytest

from tests.static import test_eko127_k01_release_runtime_bound_is_the_recorded_value as k01
from tests.static import test_eko127_k02_release_yml_changes_only_the_runtime_bound as k02
from tests.static import test_eko127_k03_nothing_outside_the_bound_changes as k03
from tests.support.fixed_pair import Throwaway

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# K-01 edges: the simulated bound is a named constant of this test, any integer different
# from the recorded 360. 300 is chosen: a realistic retune moves *down* (360 is GitHub's job
# maximum), and a value off the recorded 360 and off the literal 360 texts exercises wiring
# rather than value equality everywhere.
SIMULATED_BOUND = 300
MODULES: tuple[ModuleType, ...] = (k01, k02, k03)
K01_FILE = "test_eko127_k01_release_runtime_bound_is_the_recorded_value"

# K-04: the recorded plant-name lists, as of #138's merge — a renamed or dropped case reddens
# `test_eko130_k04_...` (the doc-check greps the same lists outside the suite).
K02_PLANT_NAMES = [
    "a-second-bound-line-in-another-job",
    "a-second-bound-line-in-the-runtime-job",
    "a-second-comment-line-above-the-bound",
    "a-step-level-timeout",
    "a-trailing-inline-comment-on-the-bound-line",
    "bound-moved-to-another-job",
    "bound-restored-to-60",
    "continue-on-error-beside-the-bound",
    "keys-reordered-in-the-runtime-job",
    "or-true-on-the-run-line",
    "publish-bound-retuned",
    "runtime-needs-changed",
    "runtime-permissions-widened",
    "the-concurrency-group-edited",
    "value-361",
    "value-boolean",
    "value-float",
    "value-negative",
    "value-quoted",
    "value-zero",
    "whitespace-only-in-another-job",
]
K03_PLANT_NAMES = [
    "a-runtime-test-added",
    "a-runtime-test-file-edited",
    "ci-runtime-checked-bound-retuned",
    "label-guard-workflow-changed",
    "runtime-conftest-changed",
    "support-helper-added",
    "support-helper-edited",
    "the-pyproject-changed",
]
K01_SHAPE_NAMES = [
    "above-the-platform-maximum",
    "boolean",
    "bound-plus-one",
    "float",
    "key-dropped",
    "negative",
    "quoted",
    "restored-to-60",
    "zero",
]

# The carrier lines are compact (`- <id without the test_eko127_ prefix>: move|pinned`) to
# stay under the lint line limit; the legend in k01's docstring gives the full tag names.
CLASS_LINE = re.compile(r"^- ([A-Za-z0-9_]+(?:\[[A-Za-z0-9_-]+\])?): (move|pinned)$")


def eko127_nodes() -> list[tuple[ModuleType, str, str]]:
    """Every collected `test_eko127_*` node of the post-task tree as (module, function, id):
    parametrize expansions included, read from the actual marks — the same surface pytest
    collects, so the classification cannot silently omit a node."""
    found: list[tuple[ModuleType, str, str]] = []
    for module in MODULES:
        for name, node in vars(module).items():
            if not (name.startswith("test_eko127_") and callable(node)):
                continue
            parameters: list[list[str]] = []
            for mark in getattr(node, "pytestmark", []):
                if mark.name == "parametrize":
                    [values] = [arg for arg in mark.args[1:]]
                    parameters.append([str(value) for value in values])
            if not parameters:
                found.append((module, name, name))
                continue
            # the house tables parametrize by one case-name list; anything else would need
            # a different expansion — asserted, not assumed
            assert len(parameters) == 1, name
            for value in parameters[0]:
                found.append((module, name, f"{name}[{value}]"))
    return found


def classification() -> dict[str, str]:
    """The docstring classification of k01's file (Q-B A carrier): node id -> tag, with the
    `test_eko127_` prefix the legend promises restored."""
    entries: dict[str, str] = {}
    for line in (k01.__doc__ or "").split("\n"):
        found = CLASS_LINE.match(line.strip())
        if found:
            short, tag = found.groups()
            node_id = f"test_eko127_{short}"
            assert node_id not in entries, f"duplicate classification for {node_id}"
            entries[node_id] = tag
    return entries


def _run_node(
    module: ModuleType,
    node_id: str,
    node_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    simulated: bool,
) -> None:
    """Call the actual eko127 node callable, supplying its fixtures the way the module's own
    recipes do. `simulated` passes SIMULATED_BOUND to the bound-parameterized callables
    (Q-A A): the live machinery moves, the record machinery's defaults never do. `node_dir`
    stays shallow — a Throwaway's repo/.git/objects chain under a long Windows path dies in
    `git hash-object`, which is a driver artifact, not a node verdict."""
    base, _, param = node_id.partition("[")
    param = param.rstrip("]")
    node = getattr(module, base)
    signature = inspect.signature(node)
    arguments: dict[str, object] = {}
    if "case" in signature.parameters:
        arguments["case"] = param
    if "tmp_path" in signature.parameters:
        arguments["tmp_path"] = node_dir
    if "monkeypatch" in signature.parameters:
        arguments["monkeypatch"] = monkeypatch
    if "throwaway" in signature.parameters:
        # the module's own `throwaway` fixture recipe: a Throwaway on the pinned head, selected
        arguments["throwaway"] = Throwaway(node_dir / "repo", k01.HEAD, monkeypatch)
    if "bound" in signature.parameters and simulated:
        arguments["bound"] = SIMULATED_BOUND
    node(**arguments)


def _verdict(
    module: ModuleType,
    node_id: str,
    node_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    simulated: bool,
) -> tuple[str, str]:
    """('green', '') | ('red', note) | ('bare', note) for one driven node. A death is *bare*
    when the failing assert is not in the test body — raised instead from plant machinery
    (`job_edit`'s `assert old in block`, `_bound_dropped`'s `assert found is not None`,
    `edit`'s `assert old in text`) — which is R-01's broken-guard noise, not a verdict."""
    base, _, _ = node_id.partition("[")
    try:
        # each node starts from a neutral environment, as in a normal pytest run
        for name in ("GIT_DIR", "GIT_WORK_TREE", "CHANGESET_BASE"):
            monkeypatch.delenv(name, raising=False)
        _run_node(module, node_id, node_dir, monkeypatch, simulated)
    except AssertionError as error:
        frames = traceback.extract_tb(error.__traceback__)
        last = frames[-1]
        if last.name != base:
            return "bare", f"{node_id}: AssertionError from {last.filename}:{last.name}"
        return "red", f"{node_id}: verdict assertion: {error}"
    # any other exception escapes and errors the driving test itself: machinery noise kills
    # the simulation just as surely, without this function swallowing it (role rule: no
    # broad except); K-01b's named deaths are all AssertionError and are classified above
    return "green", ""


def _drive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, simulated: bool
) -> tuple[set[str], list[str]]:
    """Run every eko127 node, record constants at their defaults, and return
    (red node ids, notes on any bare death or error)."""
    red: set[str] = set()
    deaths: list[str] = []
    tag = "s" if simulated else "g"
    for index, (module, _, node_id) in enumerate(eko127_nodes()):
        state, note = _verdict(
            module, node_id, tmp_path / f"{tag}{index:02d}", monkeypatch, simulated
        )
        if state == "red":
            red.add(node_id)
        elif state == "bare":
            deaths.append(note)
    return red, deaths


def _agreement(red: set[str], entries: dict[str, str]) -> list[str]:
    """The classification enforced against one red set: every red id must be classified
    must-move, every must-move id must be red, every green id must be must-stay; and every
    collected node must appear in the classification at all."""
    collected = {node_id for _, _, node_id in eko127_nodes()}
    problems = [
        f"{node_id} collected but not classified" for node_id in sorted(collected - set(entries))
    ]
    problems += [
        f"{node_id} classified but not collected" for node_id in sorted(set(entries) - collected)
    ]
    problems += [
        f"{node_id} is red under the simulated bound but classified {entries.get(node_id)}"
        for node_id in sorted(red - set(entries))
    ]
    problems += [
        f"{node_id} is red under the simulated bound but classified {entries[node_id]}"
        for node_id in sorted(red)
        if node_id in entries and entries[node_id] != "move"
    ]
    problems += [
        f"{node_id} is green under the simulated bound but classified {entries[node_id]}"
        for node_id in sorted(set(entries) - red)
        if entries[node_id] == "move"
    ]
    return problems


# K-01 -----------------------------------------------------------------------------------------


def test_eko130_k01_the_recorded_baseline_drives_every_eko127_node_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contrast half of K-01: the same driving at the recorded 360 (one element: the bound)
    yields the empty red set and no bare death — today's green suite, reached through the
    node callables rather than the runner."""
    red, deaths = _drive(tmp_path, monkeypatch, simulated=False)
    assert red == set(), sorted(red)
    assert deaths == []


def test_eko130_k01_the_simulated_bound_reddens_exactly_the_must_move_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-01c + K-02 enforcement in one: at the simulated bound the red set equals the
    classified must-move set, record nodes included — all k02/k03 nodes and k01's record
    nodes — stay green with the recorded constants unchanged, and no node dies bare."""
    red, deaths = _drive(tmp_path, monkeypatch, simulated=True)
    assert deaths == []
    entries = classification()
    assert _agreement(red, entries) == []
    assert (
        entries.get("test_eko127_k01_release_runtime_bound_is_the_live_value") == "move"
    ), "the live value check must be the simulated bound's red half"
    assert red == {node_id for node_id, tag in entries.items() if tag == "move"}


def test_eko130_k01_no_driven_eko127_node_dies_with_a_bare_assertionerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-01b stated on its own, so a retune wiring failure reads as the named defect: none of
    the 21 k02 plant cases nor `the_verdict_ignores_the_live_base` may die with an
    AssertionError raised inside plant machinery instead of by the node's own verdict."""
    for simulated in (False, True):
        _, deaths = _drive(tmp_path, monkeypatch, simulated)
        assert deaths == [], deaths


def _source(module: ModuleType) -> str:
    path = module.__file__
    assert path is not None, module.__name__
    return Path(path).read_text(encoding="utf-8")


def _bound_pair_assignments(module: ModuleType) -> dict[str, ast.expr]:
    """Top-level `NAME = value` for the bound constants, as AST: the separation is by
    wiring, not by value — the twins are both 360 today, so only the definition reaches
    M-1/M-7."""
    tree = ast.parse(_source(module))
    names = {
        "BOUND",
        "BOUND_LINE",
        "RAISE",
        "RECORDED_BOUND",
        "RECORDED_BOUND_LINE",
        "RECORDED_RAISE",
    }
    return {
        target.id: statement.value
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name) and target.id in names
    }


def _helper_call(pair: dict[str, ast.expr], name: str, helper: str, source: str) -> ast.expr:
    assert name in pair, f"{name} is not defined in the guard file"
    value = pair[name]
    assert (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == helper
        and isinstance(value.args[0], ast.Name)
        and value.args[0].id == source
    ), f"{name} must be {helper}({source}) (K-05), never a second literal or a live alias"
    return value


def test_eko130_k01_the_separation_is_by_wiring_not_by_value() -> None:
    """M-1/M-2 surface: the record constants are literals or derivations of the record pair
    only (never an alias of the live `BOUND`), the live line derives from the live value, and
    the pair-frozen k02/k03 import the record names, never the live bound constants."""
    pair = _bound_pair_assignments(k01)
    assert "RECORDED_BOUND" in pair, "the record pair must be named, not the live alias"
    recorded = pair["RECORDED_BOUND"]
    assert (
        isinstance(recorded, ast.Constant) and recorded.value == 360
    ), "RECORDED_BOUND must be the literal history, not an alias of the live BOUND"
    _helper_call(pair, "BOUND_LINE", "bound_line_of", "BOUND")
    _helper_call(pair, "RECORDED_BOUND_LINE", "bound_line_of", "RECORDED_BOUND")
    _helper_call(pair, "RECORDED_RAISE", "raise_for", "RECORDED_BOUND")
    for module in (k02, k03):
        tree = ast.parse(_source(module))
        imported = {
            alias.name
            for statement in tree.body
            if isinstance(statement, ast.ImportFrom)
            and (statement.module or "").endswith(K01_FILE)
            for alias in statement.names
        }
        live_only = imported & {"BOUND", "BOUND_LINE", "RAISE"}
        assert live_only == set(), f"{module.__name__} imports live constants {live_only}"
        if module is k02:
            assert {
                "RECORDED_BOUND",
                "RECORDED_BOUND_LINE",
                "RECORDED_RAISE",
            } <= imported, "k02 must read the record pair"
        assert "RECORDED_RAISE" in imported, "k03's simulated head must use the record raise"


# K-02 -----------------------------------------------------------------------------------------


def test_eko130_k02_the_classification_names_every_eko127_node() -> None:
    """The docstring covers the post-task tree exactly: one classification line per collected
    node, no extras, both tags known — the retune task's guidance carrier."""
    entries = classification()
    collected = {node_id for _, _, node_id in eko127_nodes()}
    assert set(entries) == collected
    assert set(entries.values()) <= {"move", "pinned"}


def test_eko130_k02_a_flipped_classification_entry_reddens_the_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-02 contrast / M-3 teeth: the agreement check is not vacuous — flipping one record
    node's entry to must-move makes it report the mismatch; flipping nothing reports none."""
    red, deaths = _drive(tmp_path, monkeypatch, simulated=True)
    assert deaths == []
    assert _agreement(red, classification()) == []
    flipped = dict(classification())
    victim = next(node_id for node_id, tag in flipped.items() if tag == "pinned")
    flipped[victim] = "move"
    assert _agreement(red, flipped) != [], victim


# K-03 -----------------------------------------------------------------------------------------


def test_eko130_k03_the_raise_annotation_does_not_overclaim_the_comment() -> None:
    """G-2 A (drop) from R-02: the claim node enforces the provenance comment's existence,
    indent, `#` prefix and position — never its bytes; no sentence in the guard file may
    claim byte-equality for the comment. M-4' (re-inserted overstatement) reddens this."""
    source = _source(k01)
    assert "same bytes" not in source
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", source))
    overclaims = [
        sentence
        for sentence in sentences
        if re.search(r"byte", sentence, re.IGNORECASE)
        and re.search(r"comment|provenance", sentence, re.IGNORECASE)
    ]
    assert overclaims == []


# K-04 -----------------------------------------------------------------------------------------


def test_eko130_k04_the_record_values_and_plant_names_are_pinned() -> None:
    """This task moved constants around but re-pinned nothing: the SHAs and the recorded 360
    keep their exact values, and every existing k02/k03 plant case name survives (the
    doc-check `tests/doc-checks/EKO-1-30.sh` repeats these reads over the branch diff)."""
    assert k01.RECORDED_BOUND == 360
    assert k01.BASE == "044e957891d5f1d256d1b9ae8e62d4f7e3f02061"
    assert k01.HEAD == "bb5f8554aa7911a626d1f428d973df067a38faff"
    assert sorted(k02.PLANTS) == K02_PLANT_NAMES
    assert sorted(k03.PLANTS) == K03_PLANT_NAMES
    assert sorted(k01.SHAPES) == K01_SHAPE_NAMES


# K-05 -----------------------------------------------------------------------------------------


def test_eko130_k05_the_simulated_move_carries_the_line_and_raise_with_the_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pair moves together, through the machinery's own derivation: a throwaway head built
    by `raise_for(SIMULATED_BOUND)` passes k02's judgment when the machinery is driven with
    the same value (the line follows the value), and fails with a line-mismatch *verdict* —
    never a bare plant death — when only the value moves (the literal-left-behind scenario
    M-7 names; under a literalized line constant inside the machinery this assert reddens)."""
    repo = Throwaway(tmp_path / "repo", k01.BASE, monkeypatch)
    moved = repo.commit(k01.BASE, k01.raise_for(SIMULATED_BOUND))
    assert k02.k02_violations(k01.BASE, moved, bound=SIMULATED_BOUND) == []
    desynced = k02.k02_violations(k01.BASE, moved, bound=k01.RECORDED_BOUND)
    assert any(
        f"{k01.TIMEOUT}: {SIMULATED_BOUND}" in problem and "is not" in problem
        for problem in desynced
    ), desynced
