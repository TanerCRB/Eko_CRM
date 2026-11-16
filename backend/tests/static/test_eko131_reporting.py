"""EKO-1-31 (#162): the realm-scan failure report names the field path, never the value.

K-01: a pytest subprocess drives the real k06 realm-scan machinery over an in-memory realm
carrying one synthetic planted secret; the captured report — rendered the way the CI static job
renders (`-v`, the backend ini in force) — contains the realm-scan AssertionError naming
`clients[0].secret` and the planted string nowhere, covering both echo channels: the helper
frame's rendered argument and the rewritten-assert breakdown. Contrast: a placeholder-form realm
runs green with no report.
K-02: detection is untouched — the fire shapes still raise AssertionError (the contract of the
two base helper users), the placeholder and absent shapes still hold.
K-03: the realm-family file collects exactly its base ids (snapshot in
`fixtures/eko131_k03_base_collection_ids.txt`, taken at base bf776ef: 242 ids); later ids are
allowed only from the eko131 family. The static-job-green verdict half is CI's.
K-04: the silence is family-scoped — an unrelated failing test still renders the standard long
breakdown with its values echoed, and the global addopts plus the ci.yml backend pytest step
carry no traceback-shaping flag.
K-06: an in-memory inventory-name + literal plant still fires the tracked secret scan
(`repo_checks.secret_assignments` — the EKO-1-29 dev-3 self-trap guard); the reference form of
the same name still holds. Plants never appear in the `NAME=value` spelling in this file.
"""

import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.test_eko112_k06_synthetic_and_secret_free import (
    assert_no_forbidden_secret_fields,
)
from tests.support import repo_checks as rc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

BACKEND = REPO_ROOT / "backend"
INI = BACKEND / "pyproject.toml"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
K06_FILE = "tests/static/test_eko112_k06_synthetic_and_secret_free.py"
SNAPSHOT = Path(__file__).parent / "fixtures" / "eko131_k03_base_collection_ids.txt"

# Synthetic plants (never real secrets, never committed under identity/), one per criterion so
# each guard stands alone. No line of this file spells an inventory name followed by `=` or
# `:` with a literal value — the K-06 in-memory plants assemble that shape at test time.
K01_PLANT = "QA131-REPORTING-PLANT-4c81"
K02_PLANT = "QA131-DETECTION-PLANT-9b37"
K06_PLANT = "QA131-ASSIGNMENT-PLANT-2f58"
SCRATCH_ECHO = "QA131-SCRATCH-ECHO-6ad0"
PLACEHOLDER_VALUE = "${CLIENT_SECRET}"
INVENTORY_NAME = "OIDC_CLIENT_SECRET"

# The children must not inherit caller-side pytest or git state; TMP* is repointed to an
# existing directory of the test — a stale harness value would break the child's own session
# directory resolution, and the child must write nothing into the repository.
DROP_ENV = {
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTHONPATH",
    "PYTEST_DEBUG_TEMPROOT",
    "CHANGESET_BASE",
    "EKO_CHECKED_IMAGES",
    "RELEASE_RECORD_TOKEN",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "TMP",
    "TEMP",
    "TMPDIR",
}


def child_env(tmp_path: Path) -> dict[str, str]:
    scratch = tmp_path / "child-temp"
    scratch.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.upper() not in DROP_ENV}
    scratch_text = str(scratch)
    env.update(TMP=scratch_text, TEMP=scratch_text, TMPDIR=scratch_text)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_pytest_child(
    tmp_path: Path, source: str, filename: str
) -> subprocess.CompletedProcess[str]:
    """One generated test module, run the way the CI static job runs pytest: `-v`, the backend
    ini in force, the same interpreter; nothing is written into the repository."""
    child = tmp_path / filename
    child.write_text(source, encoding="utf-8", newline="\n")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "-p",
        "no:cacheprovider",
        "-c",
        str(INI),
        str(child),
    ]
    result: subprocess.CompletedProcess[str] = subprocess.run(
        command,
        cwd=BACKEND,
        env=child_env(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return result


def realm_scan_child(realm: dict[str, Any]) -> str:
    """Child source calling the REAL imported helper over an in-memory realm. The realm literal
    sits at module level, mirroring the live node's render path: the rendered test-function
    frame is the call line, whose source shows only the realm name (the live node builds the
    dict with `json.loads(...)`); every value echo must therefore come from the helper frame's
    argument rendering or the rewritten-assert breakdown — the two channels K-01 claims."""
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(BACKEND)!r})\n"
        "\n"
        "from tests.static.test_eko112_k06_synthetic_and_secret_free import (\n"
        "    assert_no_forbidden_secret_fields,\n"
        ")\n"
        "\n"
        f"REALM = {realm!r}\n"
        "\n"
        "\n"
        "def test_realm_scan_child_node():\n"
        "    assert_no_forbidden_secret_fields(REALM)\n"
    )


def test_eko131_k01_failing_realm_report_names_the_path_and_holds_no_plant(
    tmp_path: Path,
) -> None:
    result = run_pytest_child(
        tmp_path,
        realm_scan_child({"clients": [{"secret": K01_PLANT}]}),
        "test_eko131_k01_child.py",
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output[-3000:]
    assert "AssertionError: clients[0].secret" in output, output[-3000:]
    assert K01_PLANT not in output


def test_eko131_k01_contrast_placeholder_realm_reports_nothing(tmp_path: Path) -> None:
    result = run_pytest_child(
        tmp_path,
        realm_scan_child({"clients": [{"secret": PLACEHOLDER_VALUE}]}),
        "test_eko131_k01_placeholder_child.py",
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-3000:]
    assert "AssertionError" not in output


@pytest.mark.parametrize("value", [None, "", "**********", K02_PLANT, 42])
def test_eko131_k02_fire_shapes_still_raise_assertion_error(value: Any) -> None:
    with pytest.raises(AssertionError):
        assert_no_forbidden_secret_fields({"clients": [{"secret": value}]})


def test_eko131_k02_contrast_placeholder_and_absent_secret_hold() -> None:
    assert_no_forbidden_secret_fields({"clients": [{"secret": PLACEHOLDER_VALUE}]})
    assert_no_forbidden_secret_fields({"clients": [{"organization": "eko131-farm"}]})
    assert_no_forbidden_secret_fields({})


def collect_ids(tmp_path: Path, target: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "-c",
        str(INI),
        target,
    ]
    result: subprocess.CompletedProcess[str] = subprocess.run(
        command,
        cwd=BACKEND,
        env=child_env(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return [line for line in result.stdout.splitlines() if "::" in line]


def collection_violations(snapshot: list[str], live: list[str]) -> list[str]:
    problems = [f"{node}: no longer collected" for node in sorted(set(snapshot) - set(live))]
    problems += [
        f"{node}: newly collected outside the eko131 family"
        for node in sorted(set(live) - set(snapshot))
        if "::test_eko131" not in node
    ]
    return problems


def test_eko131_k03_base_collection_ids_are_the_pinned_snapshot(tmp_path: Path) -> None:
    snapshot = SNAPSHOT.read_text(encoding="utf-8").splitlines()
    live = collect_ids(tmp_path, K06_FILE)
    assert snapshot and live
    assert collection_violations(snapshot, live) == []


def test_eko131_k03_the_snapshot_comparison_notices_renames_and_foreign_additions() -> None:
    base = ["tests/x.py::test_a", "tests/x.py::test_b[None-42]"]
    renamed = collection_violations(base, ["tests/x.py::test_a", "tests/x.py::test_c[None-42]"])
    assert "tests/x.py::test_b[None-42]: no longer collected" in renamed
    assert "tests/x.py::test_c[None-42]: newly collected outside the eko131 family" in renamed
    assert collection_violations(base, base + ["tests/x.py::test_eko131_added"]) == []


SCRATCH_CHILD = (
    "def test_scratch_breakdown():\n"
    f"    probe = {SCRATCH_ECHO!r}\n"
    '    assert probe == "other value"\n'
)


def test_eko131_k04_a_failure_outside_the_family_keeps_the_long_breakdown(
    tmp_path: Path,
) -> None:
    result = run_pytest_child(tmp_path, SCRATCH_CHILD, "test_eko131_k04_scratch_child.py")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output[-3000:]
    assert "def test_scratch_breakdown():" in output  # the long-form frame source block
    assert "AssertionError: assert " in output  # the rewritten breakdown line
    assert SCRATCH_ECHO in output  # the values stay echoed outside the family
    assert "other value" in output


TRACEBACK_INI_KEYS = {"tb"}


def traceback_shaping_tokens(args: list[str]) -> list[str]:
    found: list[str] = []
    for index, token in enumerate(args):
        if token.startswith("--tb"):
            found.append(token)
        elif token in {"-o", "--override"} and index + 1 < len(args):
            value = args[index + 1]
            if value.split("=", 1)[0] in TRACEBACK_INI_KEYS:
                found.append(f"{token} {value}")
    return found


def test_eko131_k04_addopts_and_the_ci_pytest_step_shape_no_traceback() -> None:
    ini: dict[str, Any] = tomllib.loads(INI.read_text(encoding="utf-8"))
    options = ini["tool"]["pytest"]["ini_options"]
    assert not TRACEBACK_INI_KEYS & set(options), "ini_options gained a tb key"
    assert traceback_shaping_tokens(shlex.split(options.get("addopts", ""))) == []
    flow: dict[str, Any] = yaml.safe_load(CI.read_text(encoding="utf-8"))
    steps = [
        step for step in flow["jobs"]["backend"]["steps"] if "pytest" in str(step.get("run", ""))
    ]
    assert len(steps) == 1, "the backend job must hold exactly one pytest step"
    words = shlex.split(str(steps[0]["run"]).strip())
    assert words[:3] == ["uv", "run", "pytest"], words
    assert traceback_shaping_tokens(words[3:]) == []


@pytest.mark.parametrize(
    "addopts", ["--tb=no", "--tb=line", "-o tb=short", "-m 'not runtime' --tb=long"]
)
def test_eko131_k04_contrast_shaped_traceback_arguments_are_detected(addopts: str) -> None:
    assert traceback_shaping_tokens(shlex.split(addopts)) != []


def test_eko131_k06_inventory_name_with_literal_value_fires_the_tracked_scan(
    secret_inventory: set[str],
) -> None:
    assert INVENTORY_NAME in secret_inventory
    line = INVENTORY_NAME + "=" + K06_PLANT
    found = rc.secret_assignments({"backend/tests/static/eko131-plant.txt": line}, secret_inventory)
    assert found != []
    assert "is assigned a value" in found[0]


def test_eko131_k06_contrast_the_reference_form_of_the_same_name_holds(
    secret_inventory: set[str],
) -> None:
    line = INVENTORY_NAME + "=" + "${" + INVENTORY_NAME + ":?}"
    found = rc.secret_assignments({"backend/tests/static/eko131-plant.txt": line}, secret_inventory)
    assert found == []
