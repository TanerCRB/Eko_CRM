"""A published release's backend, started by digest under the head's own composition, serving
its OpenAPI document directly, never through `proxy` (ADR-0004 addendum 2026-10-29; EKO-1-15 K-06).

Only the backend image digest is taken from the release's record entry (exception
EKO-1-15/security-1): a record entry is not proven to come from a release run, so its services,
volumes, mounts and depends_on never reach `docker compose`. The head's `compose.yaml` starts
`postgres`, `migrate` and `backend` under a throwaway project with `migrate` and `backend` on that
digest and a synthetic environment file for the head's composition (scripts/dev-env.sh), and is
removed with its volumes afterwards. Pulling the image needs a registry login with read access
(the workflow's step). Any failure is CannotTell: a release whose document cannot be obtained is
never "no release".
"""

import json
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.support.releases import CannotTell, Release, backend_reference
from tests.support.repo import REPO_ROOT, compose_env, write_synthetic_env

START_SECONDS = 600
FETCH = (
    "import sys, urllib.request\n"
    "with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=10) as r:\n"
    "    sys.stdout.write(r.read().decode('utf-8'))\n"
)
HEAD_COMPOSITION = REPO_ROOT / "compose.yaml"
# The head's services that run the backend image; `backend` builds on `up` unless reset.
BACKEND_IMAGE_SERVICES = ("migrate", "backend")

Compose = Callable[..., subprocess.CompletedProcess[str]]


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


def backend_override(image: str) -> str:
    """The head's backend-image services on `image`, pulled if absent, never built."""
    lines = ["services:"]
    for service in BACKEND_IMAGE_SERVICES:
        lines += [f"  {service}:", f"    image: {image}", "    pull_policy: missing"]
        if service == "backend":
            lines.append("    build: !reset null")
    return "\n".join(lines) + "\n"


def served_document(found: Release, compose: Compose = _compose) -> Any:
    image = backend_reference(found)
    with tempfile.TemporaryDirectory(prefix="eko-release-") as directory:
        override = Path(directory) / "previous-backend.yaml"
        override.write_text(backend_override(image), encoding="utf-8")
        env_file = Path(directory) / "synthetic.env"
        try:
            write_synthetic_env(env_file)
        except subprocess.CalledProcessError:
            raise CannotTell("no synthetic environment for the head's composition") from None
        project = f"eko-compat-{uuid.uuid4().hex[:8]}"
        base = ["docker", "compose", "-f", str(HEAD_COMPOSITION), "-f", str(override)]
        base += ["-p", project, "--env-file", str(env_file)]
        try:
            up = compose(
                base, "up", "-d", "--wait", "--wait-timeout", str(START_SECONDS), "backend",
                timeout=START_SECONDS + 120,
            )  # fmt: skip
            if up.returncode != 0:
                raise CannotTell(f"{found.tag}: its backend did not start (exit {up.returncode})")
            fetched = compose(base, "exec", "-T", "backend", "python", "-c", FETCH)
            if fetched.returncode != 0:
                raise CannotTell(f"{found.tag}: its backend did not serve its OpenAPI document")
            try:
                return json.loads(fetched.stdout)
            except ValueError:
                raise CannotTell(f"{found.tag}: its OpenAPI document is not JSON") from None
        finally:
            compose(base, "down", "-v", "--remove-orphans")
