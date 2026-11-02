"""EKO-1-13 runtime helpers: container log windows, scripts run in the backend image, and the
fixture variant image (ADR-0005 addendum 2026-11-02, *Under `serve.py`'s process configuration*).

A window is the part of a container's log written after a mark, so a test reads only the lines
its own requests caused, never another test's.
"""

import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Any

from tests.runtime.conftest import Composition
from tests.runtime.lab import Lab, docker
from tests.support.repo import REPO_ROOT

FIXTURE_MODULE = REPO_ROOT / "backend" / "tests" / "support" / "fixture_app.py"
FIXTURE_IMPORT = "eko113_fixture_app"


def container_log(container: str) -> str:
    result = docker("logs", container, check=False, timeout=120)
    return result.stdout + result.stderr


@dataclass
class Window:
    container: str
    start: int

    def text(self, settle: float = 1.0) -> str:
        """The lines written since the mark; waits `settle` seconds for late lines first."""
        time.sleep(settle)
        return "\n".join(container_log(self.container).splitlines()[self.start :])


def window(composition: Composition, service: str) -> Window:
    container = composition.container_id(service)
    return Window(container, len(container_log(container).splitlines()))


def python_in_service(
    composition: Composition, service: str, script: str, *args: str, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    """A script on stdin (never on a command line, so no value it holds is in a process list)."""
    return composition.compose(
        "exec", "-T", service, "python", "-", *args, stdin=script, check=False, timeout=timeout
    )


def json_result(result: subprocess.CompletedProcess[str]) -> Any:
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, f"no result: {result.stdout[-2000:]} {result.stderr[-2000:]}"
    return json.loads(lines[-1])


def fixture_image(lab: Lab) -> str:
    """The shipped backend image plus the fixture module, and nothing else."""
    name = "eko113_fixture"
    if name in lab.images:
        return lab.images[name]
    context = lab.workdir / "variants" / name
    context.mkdir(parents=True)
    (context / f"{FIXTURE_IMPORT}.py").write_bytes(FIXTURE_MODULE.read_bytes())
    (context / "Dockerfile").write_text(
        f"FROM {lab.shipped_image}\nCOPY {FIXTURE_IMPORT}.py /app/{FIXTURE_IMPORT}.py\n",
        encoding="utf-8",
    )
    tag = f"localhost/eko-crm/backend-variant:{lab.composition.project}-{name}"
    docker("build", "-q", "-t", tag, str(context), timeout=600)
    lab.images[name] = tag
    return tag


def serve_command(factory: str) -> list[str]:
    """The shipped `serve.main`, given the fixture's factory: the only element that differs."""
    return ["python", "-c", f"from app import serve; serve.main('{FIXTURE_IMPORT}:{factory}')"]


def backend_as(lab: Lab, image: str, command: list[str] | None) -> Composition:
    """The lab's composition with `backend` running `image` (and `command`, if given)."""
    override = lab.workdir / f"backend-{uuid.uuid4().hex[:8]}.yaml"
    # `backend` builds on `up` (pull_policy: build): the override must run the variant as given.
    lines = ["services:", "  backend:", f"    image: {image}", "    pull_policy: never"]
    if command is not None:
        lines.append(f"    command: {json.dumps(command)}")
    override.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Composition(lab.composition.project, lab.composition.env_file, [override])


def restore_backend(lab: Lab) -> None:
    lab.composition.compose("up", "-d", "--no-deps", "--force-recreate", "backend", check=False)


def get_in_network(
    lab: Lab, url: str, headers: dict[str, str] | None = None, body: str | None = None
) -> dict[str, Any]:
    """A request from the prober container (a POST when `body` is given): status, headers and
    body, as JSON."""
    script = (
        "import json, sys, urllib.error, urllib.request\n"
        "data = sys.argv[3].encode() if len(sys.argv) > 3 else None\n"
        "request = urllib.request.Request(sys.argv[1], data, json.loads(sys.argv[2]))\n"
        "try:\n"
        "    response = urllib.request.urlopen(request, timeout=10)\n"
        "except urllib.error.HTTPError as exc:\n"
        "    response = exc\n"
        "out = {'status': response.status, 'headers': dict(response.headers.items()),\n"
        "       'body': response.read().decode('utf-8', 'replace')}\n"
        "print(json.dumps(out))  # leftovers-allow: container probe; stdout is its answer\n"
    )
    args = [url, json.dumps(headers or {}), *([] if body is None else [body])]
    result = docker("exec", lab.prober, "python", "-c", script, *args, check=False)
    return dict(json_result(result))


def wait_for_status(lab: Lab, url: str, status: int, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    last: object = None
    while time.monotonic() < deadline:
        try:
            last = get_in_network(lab, url)["status"]
        except AssertionError as exc:
            last = str(exc)[:200]
        if last == status:
            return
        time.sleep(0.5)
    raise AssertionError(f"{url}: {last!r}, not {status}, after {seconds} s")
