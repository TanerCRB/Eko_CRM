"""A published release's backend, started by digest from its own release composition, serving its
OpenAPI document directly, never through `proxy` (ADR-0004 addendum 2026-10-29; EKO-1-15 K-06).

The composition starts `postgres`, `migrate` and `backend` of the release under a throwaway
project with a synthetic environment file (scripts/dev-env.sh), and is removed with its volumes
afterwards. Pulling the images needs a registry login with read access (the workflow's step).
Any failure is CannotTell: a release whose document cannot be obtained is never "no release".
"""

import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from tests.support.releases import CannotTell, Release, backend_reference
from tests.support.repo import compose_env, write_synthetic_env

START_SECONDS = 600
FETCH = (
    "import sys, urllib.request\n"
    "with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=10) as r:\n"
    "    sys.stdout.write(r.read().decode('utf-8'))\n"
)


def _compose(base: list[str], *args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [*base, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=compose_env(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CannotTell(f"docker compose {args[0]}: {type(error).__name__}") from None


def served_document(found: Release) -> Any:
    backend_reference(found)
    with tempfile.TemporaryDirectory(prefix="eko-release-") as directory:
        composition = Path(directory) / "compose.release.yaml"
        composition.write_text(found.composition, encoding="utf-8")
        env_file = Path(directory) / "synthetic.env"
        try:
            write_synthetic_env(env_file, compose_file=composition)
        except subprocess.CalledProcessError:
            raise CannotTell(f"{found.tag}: no synthetic environment for its composition") from None
        project = f"eko-compat-{uuid.uuid4().hex[:8]}"
        base = ["docker", "compose", "-f", str(composition), "-p", project]
        base += ["--env-file", str(env_file)]
        try:
            up = _compose(
                base, "up", "-d", "--wait", "--wait-timeout", str(START_SECONDS), "backend",
                timeout=START_SECONDS + 120,
            )  # fmt: skip
            if up.returncode != 0:
                raise CannotTell(f"{found.tag}: its backend did not start (exit {up.returncode})")
            fetched = _compose(base, "exec", "-T", "backend", "python", "-c", FETCH)
            if fetched.returncode != 0:
                raise CannotTell(f"{found.tag}: its backend did not serve its OpenAPI document")
            try:
                return json.loads(fetched.stdout)
            except ValueError:
                raise CannotTell(f"{found.tag}: its OpenAPI document is not JSON") from None
        finally:
            _compose(base, "down", "-v", "--remove-orphans")
