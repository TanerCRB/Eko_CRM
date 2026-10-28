"""Runtime harness: the composition started by the documented command, from no volumes.

Each composition gets its own project name, a fresh synthetic environment file outside the
repository and free host ports, and is removed with its volumes afterwards.
"""

import json
import re
import secrets
import socket
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.support.repo import REPO_ROOT, write_synthetic_env

UP_TIMEOUT_SECONDS = 900
PORT_VARIABLES = ("PROXY_HTTP_PORT", "PROXY_HTTPS_PORT", "PROXY_ADMIN_PORT")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


def read_env(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return {name: value for name, value in pairs}


def write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")


def make_env_file(directory: Path) -> Path:
    path = write_synthetic_env(directory / "synthetic.env")
    values = read_env(path)
    for name in PORT_VARIABLES:
        values[name] = str(free_port())
    write_env(path, values)
    return path


def parse_instant(value: str) -> datetime:
    """Docker's RFC 3339 with nanoseconds, cut to microseconds."""
    trimmed = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    return datetime.fromisoformat(trimmed)


@dataclass
class Composition:
    project: str
    env_file: Path
    extra_files: list[Path] = field(default_factory=list)

    @property
    def env(self) -> dict[str, str]:
        return read_env(self.env_file)

    def base_args(self) -> list[str]:
        args = ["docker", "compose"]
        if self.extra_files:
            args += ["-f", str(REPO_ROOT / "compose.yaml")]
            for extra in self.extra_files:
                args += ["-f", str(extra)]
        return args + ["-p", self.project, "--env-file", str(self.env_file), "--profile", "dev"]

    def compose(
        self, *args: str, check: bool = True, stdin: str | None = None, timeout: int = 300
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [*self.base_args(), *args],
            cwd=REPO_ROOT,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and result.returncode != 0:
            command = " ".join(args)
            raise AssertionError(
                f"docker compose {command} exited {result.returncode}\n{result.stderr[-3000:]}"
            )
        return result

    def container_id(self, service: str) -> str:
        ids = self.compose("ps", "-a", "-q", service).stdout.split()
        assert len(ids) == 1, f"{service}: {ids}"
        return ids[0]

    def inspect(self, service: str) -> dict[str, Any]:
        out = subprocess.run(
            ["docker", "inspect", self.container_id(service)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        inspected: dict[str, Any] = json.loads(out)[0]
        return inspected

    def container_env(self, service: str) -> dict[str, str]:
        pairs = (item.split("=", 1) for item in self.inspect(service)["Config"]["Env"])
        return {name: value for name, value in pairs}

    def sql(self, query: str, database: str = "eko") -> list[list[str]]:
        """A query as the superuser over the container's local socket."""
        result = self.compose(
            "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", database,
            "-AtX", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-c", query,
        )  # fmt: skip
        return [line.split("\t") for line in result.stdout.splitlines() if line]

    def python_in_backend(self, script: str) -> subprocess.CompletedProcess[str]:
        """Run a script in the backend container; it arrives on stdin, never on a command line."""
        return self.compose("exec", "-T", "backend", "python", "-", stdin=script, check=False)

    def fetch_in_network(self, url: str) -> str:
        """GET from inside the composition network, from the proxy container (busybox wget)."""
        return self.compose("exec", "-T", "proxy", "wget", "-qO-", url).stdout

    def through_proxy(
        self, listener: str, path: str, method: str = "GET", host: str | None = None
    ) -> httpx.Response:
        """A request to one of proxy's host ports, with the listener's host name as SNI and Host."""
        env = self.env
        port, name, scheme = {
            "app": (env["PROXY_HTTPS_PORT"], env["APP_HOST"], "https"),
            "auth": (env["PROXY_HTTPS_PORT"], env["AUTH_HOST"], "https"),
            "admin": (env["PROXY_ADMIN_PORT"], env["AUTH_ADMIN_HOST"], "https"),
            "http": (env["PROXY_HTTP_PORT"], env["APP_HOST"], "http"),
        }[listener]
        host = host or name
        url = httpx.URL(scheme=scheme, host="127.0.0.1", port=int(port), raw_path=path.encode())
        extensions = {"sni_hostname": host} if scheme == "https" else {}
        with httpx.Client(verify=False, timeout=15, follow_redirects=False) as client:
            request = client.build_request(method, url, headers={"Host": host})
            request.extensions.update(extensions)
            return client.send(request)

    def down(self) -> None:
        self.compose("down", "-v", "--remove-orphans", check=False, timeout=300)


def new_composition(tmp_path_factory: pytest.TempPathFactory, label: str) -> Composition:
    directory = tmp_path_factory.mktemp(label)
    project = f"ekort-{label}-{uuid.uuid4().hex[:8]}"
    return Composition(project=project, env_file=make_env_file(directory))


@dataclass
class Started:
    composition: Composition
    up: subprocess.CompletedProcess[str]


@pytest.fixture(scope="session")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Started]:
    """The development profile, started by the documented command from no volumes."""
    composition = new_composition(tmp_path_factory, "dev")
    try:
        up = composition.compose(
            "up", "--build", "--wait", "--wait-timeout", str(UP_TIMEOUT_SECONDS),
            check=False, timeout=UP_TIMEOUT_SECONDS + 300,
        )  # fmt: skip
        if up.returncode != 0:
            logs = composition.compose("logs", "--tail", "40", check=False).stdout
            raise AssertionError(f"up exited {up.returncode}\n{up.stderr[-3000:]}\n{logs[-6000:]}")
        yield Started(composition, up)
    finally:
        composition.down()


@pytest.fixture
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Composition]:
    """A separate composition for a scenario that must start from no volumes of its own."""
    composition = new_composition(tmp_path_factory, "fresh")
    try:
        yield composition
    finally:
        composition.down()


def random_marker() -> str:
    return "marker-" + secrets.token_hex(6)
