"""K-04 harness: the double's recorder hands every request of the backup account to sftp-server
with the flags of the destination fragment kept for the IT department (ADR-0004 addendum
2026-10-30, *The destination double*, amended at gate 1). The double proves nothing about the
fragment itself; this keeps the two from drifting apart.
"""

import re
import shlex

from tests.support.repo import REPO_ROOT

DOUBLE = REPO_ROOT / "backend" / "tests" / "runtime" / "destination_double"


def fragment_flags(text: str) -> list[str]:
    [line] = [line for line in text.splitlines() if line.strip().startswith("ForceCommand")]
    words = shlex.split(line)
    assert words[:2] == ["ForceCommand", "internal-sftp"], words
    return words[2:]


def recorder_flags(text: str) -> list[str]:
    allow = re.search(r'^ALLOW_LIST = "([^"]+)"$', text, re.MULTILINE)
    flags = re.search(r"^DESTINATION_FLAGS = \[(.*)\]$", text, re.MULTILINE)
    assert allow is not None and flags is not None
    return [
        allow.group(1) if f == "ALLOW_LIST" else f.strip('"') for f in flags.group(1).split(", ")
    ]


def test_k04_double_runs_the_fragments_sftp_server_flags() -> None:
    fragment = (DOUBLE / "it-destination-fragment.conf").read_text(encoding="utf-8")
    recorder = (DOUBLE / "recorder.py").read_text(encoding="utf-8")
    assert fragment_flags(fragment) == recorder_flags(recorder)
    assert fragment_flags(fragment) == [
        "-l", "VERBOSE", "-u", "0377", "-p", "open,write,close,stat,lstat,fstat,realpath"
    ]  # fmt: skip


def test_k04_double_flag_check_fails_on_a_widened_allow_list() -> None:
    fragment = (DOUBLE / "it-destination-fragment.conf").read_text(encoding="utf-8")
    recorder = (
        (DOUBLE / "recorder.py")
        .read_text(encoding="utf-8")
        .replace(",realpath", ",realpath,remove")
    )
    assert fragment_flags(fragment) != recorder_flags(recorder)
