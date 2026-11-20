"""EKO-1-35: a throwaway copy of the backend and of `frontend/src/api/`, edited, then judged.

A drift planted here is judged on the OpenAPI document generated from the edited source by the
check's own command (`python -m tests.support.frontend_contract`), never on a stored document;
the real tree is only read. This module imports nothing from `app/`.
"""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.support.repo import REPO_ROOT

# What the command needs: the application, the support package it runs from, the frontend sources.
COPIED = ("backend/app", "backend/tests/__init__.py", "backend/tests/support", "frontend/src/api")
COMMAND = ("-m", "tests.support.frontend_contract")
GENERATE = (
    "import json, sys\n"
    "from tests.support.api_surface import real_app\n"
    "sys.stdout.write(json.dumps(real_app().openapi(), sort_keys=True))\n"
)
TIMEOUT_SECONDS = 300
# Each edit: a repository-relative path, the text it must hold exactly once, and its replacement.
Edits = Mapping[str, tuple[str, str]]


def copied_tree(target: Path, edits: Edits, source: Path = REPO_ROOT) -> Path:
    for relative in COPIED:
        origin, copy = source / relative, target / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, copy, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(origin, copy)
    for relative, (old, new) in edits.items():
        file = target / relative
        text = file.read_bytes().decode("utf-8")
        if text.count(old) != 1:
            raise ValueError(f"{relative}: {old!r} occurs {text.count(old)} times, not once")
        file.write_bytes(text.replace(old, new).encode("utf-8"))
    return target


def environment() -> dict[str, str]:
    """The caller's environment minus every `APP_*` setting, as CI's own command runs."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("APP_")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *COMMAND],
        cwd=root / "backend",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment(),
        timeout=TIMEOUT_SECONDS,
    )


def generated_document(root: Path) -> dict[str, Any]:
    """The document `create_app()` of the tree under `root` generates; a failure raises."""
    result = subprocess.run(
        [sys.executable, "-c", GENERATE],
        cwd=root / "backend",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment(),
        timeout=TIMEOUT_SECONDS,
        check=True,
    )
    document: dict[str, Any] = json.loads(result.stdout)
    return document
