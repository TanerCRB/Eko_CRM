"""Repository access for the static checks: the files Git tracks and the rendered composition."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_ENV_SCRIPT = REPO_ROOT / "scripts" / "dev-env.sh"


def git(*args: str, cwd: Path = REPO_ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def tracked_files() -> list[str]:
    """Files Git tracks, plus new files it would track; never ignored ones (.venv, node_modules)."""
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    return sorted({p for p in listed if p and (REPO_ROOT / p).is_file()})


def read_text(relative: str) -> str | None:
    try:
        return (REPO_ROOT / relative).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return None


def bash() -> str:
    found = shutil.which("bash")
    if found is None:
        raise RuntimeError("bash is required to generate the synthetic environment file")
    return found


def write_synthetic_env(target: Path, compose_file: Path | None = None) -> Path:
    env = dict(os.environ)
    if compose_file is not None:
        env["COMPOSE_FILE_PATH"] = str(compose_file)
    subprocess.run([bash(), str(DEV_ENV_SCRIPT), str(target)], check=True, env=env)
    return target


def compose_env() -> dict[str, str]:
    # The repository's composition only: no file list or profile from the caller's shell.
    env = dict(os.environ)
    for name in ("COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME"):
        env.pop(name, None)
    return env


def render(
    env_file: Path | None,
    *,
    dev_profile: bool,
    interpolate: bool = True,
    compose_file: Path | None = None,
) -> dict[str, Any]:
    """`docker compose config` as JSON. Without `compose_file` it runs in the repository root, so
    auto-loaded override files are part of what is checked."""
    args = ["docker", "compose"]
    if compose_file is not None:
        args += ["-f", str(compose_file)]
    if env_file is not None:
        args += ["--env-file", str(env_file)]
    if dev_profile:
        args += ["--profile", "dev"]
    args += ["config", "--format", "json"]
    if not interpolate:
        args.append("--no-interpolate")
    result = subprocess.run(
        args, cwd=REPO_ROOT, check=True, capture_output=True, text=True, env=compose_env()
    )
    rendered: dict[str, Any] = json.loads(result.stdout)
    return rendered
