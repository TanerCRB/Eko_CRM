"""EKO-1-14 fix round 1: static rules on the shipped backup script and its line endings.

- F-01: the files an image or the double runs without a `.sh` suffix are checked out with LF on
  every platform, or a Windows checkout builds a `backup` image whose shebang ends in CR.
- S-02 (rule 19): no value is interpolated into a statement on the control session except the
  lock key, which is validated as a signed integer before use.
- The naming rule's random part: 16 hexadecimal digits from the kernel's random source.
"""

import re
import subprocess

import pytest

from tests.support.repo import REPO_ROOT

SCRIPT = REPO_ROOT / "backup" / "eko-backup"
LF_FILES = [
    "backup/eko-backup",
    "backup/schedule",
    "backup/entrypoint.sh",
    "backend/tests/runtime/destination_double/Dockerfile",
    "backend/tests/runtime/destination_double/sshd_config",
    "backend/tests/runtime/destination_double/start.sh",
    "backend/tests/runtime/destination_double/recorder.py",
    "backend/tests/runtime/destination_double/it-destination-fragment.conf",
]
CTL_CALL = re.compile(r'^\s*ctl "((?:[^"\\]|\\.)*)"', re.MULTILINE)
INTERPOLATION = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|([A-Za-z_][A-Za-z0-9_]*)|\()")
ALLOWED = {"key"}
KEY_CHECK = '[[ "$key" =~ ^-?[0-9]{1,19}$ ]]'


def eol(path: str) -> str:
    out = subprocess.run(
        ["git", "check-attr", "eol", "--", path],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return out.rsplit(":", 1)[1].strip()


@pytest.mark.parametrize("path", LF_FILES)
def test_f01_runtime_files_without_sh_suffix_are_checked_out_with_lf(path: str) -> None:
    assert eol(path) == "lf"


def test_f01_contrast_a_file_not_listed_has_no_eol_attribute() -> None:
    assert eol("backup/README.md") == "unspecified"


def sql_interpolations(script: str) -> list[str]:
    """Names interpolated into `ctl "..."` statements, other than the validated lock key."""
    found = []
    for statement in CTL_CALL.findall(script):
        for match in INTERPOLATION.finditer(statement):
            name = match.group(1) or match.group(2) or "$("
            if name not in ALLOWED:
                found.append(name)
    return found


def test_s02_no_value_but_the_lock_key_is_interpolated_into_sql() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert CTL_CALL.findall(script), "no control-session statement found"
    assert sql_interpolations(script) == []
    assert KEY_CHECK in script
    assert script.index(KEY_CHECK) < script.index('ctl "SELECT pg_advisory_lock(')


@pytest.mark.parametrize(
    "planted",
    ['  ctl "SELECT $OTHER" || ctl_fail lock\n', '  ctl "SELECT ${SET_NAME}"\n',
     '  ctl "SELECT $(cat /x)"\n'],
)  # fmt: skip
def test_s02_contrast_a_planted_interpolation_is_found(planted: str) -> None:
    script = SCRIPT.read_text(encoding="utf-8") + planted
    assert sql_interpolations(script) != []


def test_naming_rule_random_part_is_16_hex_digits_from_the_kernel() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    [assignment] = [
        line for line in script.splitlines() if line.strip().startswith('SET_NAME="eko-')
    ]
    assert r"$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')" in assignment
    assert "[0-9a-f]{16}$ ]]" in script
