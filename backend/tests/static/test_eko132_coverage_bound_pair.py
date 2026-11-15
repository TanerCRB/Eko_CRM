"""EKO-1-32 (#166): the simulation's module surface is checked against the disk, and every
k01 `bound_violations` call site is pinned to its declared constant pair.

R-01's second half: `eko127_nodes()` iterates the imported `MODULES` only, so a new
`test_eko127_*.py` file on disk sat silently outside every node of the simulation; K-02
(gate 1 G-2 A) turns the disk glob into a named check. R-02: the helper's default pointed
at the LIVE pair, so a future record call site that dropped the argument or named `BOUND`
stayed green at rest and under the simulation — while the twins are both 360, no value- or
drive-based test can see which constant a call received (the M-1a/M-1b precedent), so K-03
(gate 1 G-1 A) makes `bound` a required parameter and K-04 reads the declared pair off the
AST of every call argument.
"""

import ast
import inspect
from pathlib import Path

import pytest

from tests.static import test_eko127_k01_release_runtime_bound_is_the_recorded_value as k01
from tests.static import test_eko130_retune_simulation_separates_live_from_record as sim

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# the scan's single exclusion, by full node name (K-04: never by prefix); its `bound`
# parameter is the Q-A A driver contract (gate 1 of #152) and out of scope to change
LIVE_NODE = "test_eko127_k01_release_runtime_bound_is_the_live_value"


def _static_dir() -> Path:
    path = sim.__file__
    assert path is not None, sim.__name__
    return Path(path).parent


def test_eko132_k02_the_modules_declaration_covers_every_eko127_file_on_disk() -> None:
    """G-2 A (R-01's silent escape): every `test_eko127_*.py` stem on disk is in `MODULES`
    and every declared module is on disk — a planted module reddens this node naming its
    stem, until its nodes are declared and classified."""
    on_disk = {path.stem for path in _static_dir().glob("test_eko127_*.py")}
    declared = {module.__name__.rpartition(".")[2] for module in sim.MODULES}
    assert on_disk == declared, (
        f"undeclared test_eko127_*.py on disk: {sorted(on_disk - declared)}; "
        f"declared but not on disk: {sorted(declared - on_disk)}"
    )


def test_eko132_k03_the_bound_argument_of_bound_violations_is_required() -> None:
    """G-1 A (R-02's first mutation): with no default, a call site that drops the pair is a
    TypeError at once — at rest and under the simulation — not a silent read of the live
    value; every site must declare which pair it judges against."""
    parameter = inspect.signature(k01.bound_violations).parameters["bound"]
    assert parameter.default is inspect.Parameter.empty, (
        f"bound_violations defaults bound to {parameter.default!r}; a default points at a "
        "pair its call sites never declared (EKO-1-32 K-03)"
    )


def _bound_violations_calls(scope: ast.AST) -> list[ast.Call]:
    return [
        statement
        for statement in ast.walk(scope)
        if isinstance(statement, ast.Call)
        and isinstance(statement.func, ast.Name)
        and statement.func.id == "bound_violations"
    ]


def _bound_argument(call: ast.Call) -> ast.expr:
    """The bound argument of a `bound_violations` call — second positional or `bound=`
    keyword (K-03 edges: both forms are explicit); a call that drops it is named."""
    positional = call.args[1] if len(call.args) >= 2 else None
    keywords = [kw.value for kw in call.keywords if kw.arg == "bound"]
    assert not (positional is not None and keywords), ast.unparse(call)
    argument = positional if positional is not None else keywords[0] if keywords else None
    assert argument is not None, f"call drops its bound argument: {ast.unparse(call)}"
    return argument


def test_eko132_k04_no_record_call_site_reads_the_live_pair() -> None:
    """R-02's second mutation (M-5), AST-only while the twins are both 360: every record
    site's bound argument is the Name `RECORDED_BOUND`, and the one excluded live node
    passes through its own `bound` parameter — a site naming `BOUND` stays green to every
    value- and drive-based test, so this scan is its only tooth."""
    tree = ast.parse(sim._source(k01))
    live_defs = [
        statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef) and statement.name == LIVE_NODE
    ]
    assert len(live_defs) == 1, f"k01 must carry exactly one {LIVE_NODE} (the scan's exclusion)"
    problems: list[str] = []
    for statement in tree.body:
        is_live = statement in live_defs
        expected = "bound" if is_live else "RECORDED_BOUND"
        if is_live:
            scope_name = LIVE_NODE
        elif isinstance(statement, ast.FunctionDef):
            scope_name = statement.name
        else:
            scope_name = "module level"
        for call in _bound_violations_calls(statement):
            argument = _bound_argument(call)
            if not (isinstance(argument, ast.Name) and argument.id == expected):
                problems.append(
                    f"{scope_name}:{call.lineno} passes {ast.unparse(argument)}, "
                    f"expected the Name {expected}"
                )
    assert problems == [], problems
