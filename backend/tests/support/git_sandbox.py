"""A throwaway Git repository holding copies of the real layer check and layer table."""

import os
import shutil
import subprocess
from pathlib import Path

from tests.support.repo import REPO_ROOT, bash

COPIED = ("scripts/layer-check.sh", "docs/architecture/layer-dependencies.md")


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        for relative in COPIED:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / relative, target)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "user.email", "sandbox@example.com")
        self.git("config", "user.name", "sandbox")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout

    def commit(self, files: dict[str, str], message: str = "change") -> str:
        for relative, text in files.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def append(self, relative: str, line: str) -> dict[str, str]:
        text = (self.root / relative).read_text(encoding="utf-8")
        return {relative: text + line + "\n"}

    def run(self, script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        """Runs a workflow step's `run` text the way the runner does: bash, from the checkout."""
        return subprocess.run(
            [bash(), "-c", script],
            cwd=self.root,
            capture_output=True,
            text=True,
            env={**_inherited_env(), **env},
        )


def _inherited_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in {"BASE", "HEAD"}}
