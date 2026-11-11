"""Runtime harness: the composition started by the documented bring-up, from no volumes.

Each composition gets its own project name, a fresh synthetic environment file outside the
repository and free host ports, and is removed with its volumes afterwards.
"""

import functools
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from tests.support.repo import REPO_ROOT, write_synthetic_env

if TYPE_CHECKING:
    from tests.runtime.backup_lab import BackupLab
    from tests.runtime.lab import Lab

UP_TIMEOUT_SECONDS = 900
PORT_VARIABLES = ("PROXY_HTTP_PORT", "PROXY_HTTPS_PORT", "PROXY_ADMIN_PORT")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """EKO-1-13 K-07: the secret-in-logs check reads the logs every other test left behind."""
    last = [item for item in items if "test_adr0005_no_secret_in_logs" in item.nodeid]
    items[:] = [item for item in items if item not in last] + last


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


def make_env_file(directory: Path, project: str) -> Path:
    path = write_synthetic_env(directory / "synthetic.env")
    values = read_env(path)
    for name in PORT_VARIABLES:
        values[name] = str(free_port())
    # One backend image per test composition: a rebuild in one never swaps another's image.
    values["COMPOSE_PROJECT_NAME"] = project
    values["BACKEND_IMAGE_TAG"] = f"0.1.0-{project}"
    write_env(path, values)
    return path


def parse_instant(value: str) -> datetime:
    """Docker's RFC 3339 with nanoseconds, cut to microseconds."""
    trimmed = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    return datetime.fromisoformat(trimmed)


# EKO-1-15 K-02 (ADR-0004-C31): in a release run the runtime tests run the images built once and
# checked, loaded under the names EKO_CHECKED_IMAGES gives, and never rebuild them.
# EKO-1-26 K-01 and K-02 (route A): the custom Keycloak image joins the placed family — it too
# is built and identity-verified outside the session, so the session never builds it in session.
CHECKED_SERVICES = {
    "proxy": "proxy",
    "frontend": "frontend",
    "backup": "backup",
    "backend": "backend",
    "migrate": "backend",
    "worker": "backend",
    "keycloak": "keycloak",
}
BUILT_SERVICES = ("proxy", "frontend", "backup", "backend", "keycloak")


@functools.cache
def checked_images_override() -> Path | None:
    """A composition override naming the checked images, or None outside a release run."""
    given = os.environ.get("EKO_CHECKED_IMAGES", "").split()
    if not given:
        return None
    images = dict(item.split("=", 1) for item in given if "=" in item)
    missing = sorted(set(CHECKED_SERVICES.values()) - set(images))
    if missing:
        raise ValueError(f"EKO_CHECKED_IMAGES names no image for {', '.join(missing)}")
    lines = ["services:"]
    for service, name in CHECKED_SERVICES.items():
        lines += [f"  {service}:", f"    image: {images[name]}", "    pull_policy: never"]
        if service in BUILT_SERVICES:
            lines.append("    build: !reset null")
        if service == "backup":
            # The manifest names the images the composition actually runs, as the anchors do.
            # EKO-1-26 K-02 (C-4 edge): keycloak's manifest name mirrors the placed checked image
            # exactly like backend's, so the release-mode manifest never names a non-running image.
            lines += [
                "    environment:",
                f"      BACKUP_MANIFEST_BACKEND_IMAGE: {images['backend']}",
                f"      BACKUP_MANIFEST_KEYCLOAK_IMAGE: {images['keycloak']}",
            ]
    override = Path(tempfile.mkdtemp(prefix="eko-checked-")) / "checked-images.yaml"
    override.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return override


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
        checked = checked_images_override()
        extra_files = ([checked] if checked else []) + self.extra_files
        if extra_files:
            args += ["-f", str(REPO_ROOT / "compose.yaml")]
            for extra in extra_files:
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
        self,
        listener: str,
        path: str,
        method: str = "GET",
        host: str | None = None,
        headers: dict[str, str] | None = None,
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
            request = client.build_request(method, url, headers={"Host": host, **(headers or {})})
            request.extensions.update(extensions)
            return client.send(request)

    def down(self) -> None:
        self.compose("down", "-v", "--remove-orphans", check=False, timeout=300)


def new_composition(tmp_path_factory: pytest.TempPathFactory, label: str) -> Composition:
    directory = tmp_path_factory.mktemp(label)
    project = f"ekort-{label}-{uuid.uuid4().hex[:8]}"
    return Composition(project=project, env_file=make_env_file(directory, project))


@dataclass
class Started:
    composition: Composition
    up: subprocess.CompletedProcess[str]


@pytest.fixture(scope="session")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Started]:
    """The development profile, brought up the accepted two-step way from no volumes.

    EKO-1-12 (ADR-0004 addendum of 2026-11-02): `compose up` alone leaves both proxy listeners
    closed — each opens only after its own live brute-force precondition — so the session
    bring-up runs `prepare` and then `scripts/keycloak-bootstrap.sh`, exactly like
    `keycloak_running`. `prepare` must stay the first step: it keeps Keycloak out of the up,
    so the server's first start of an empty database happens inside the bootstrap's own
    override recreate, where the temporary administrator is the one the script answers.
    A contrast that needs an un-bootstrapped composition must use `fresh` or its own project,
    never this fixture. The two final assertions are the live precondition this whole session
    depends on: if bootstrap ever returns success on a composition whose listeners are closed,
    the fixture fails here instead of handing out the closed sockets behind 100+ connection
    errors.
    """
    from tests.runtime.keycloak_client import listener_open, prepare, run_bootstrap

    composition = new_composition(tmp_path_factory, "dev")
    try:
        prepare(composition)
        result = run_bootstrap(composition)
        assert listener_open(composition, "admin"), "admin listener closed after bootstrap"
        assert listener_open(composition, "auth"), "public listener closed after bootstrap"
        yield Started(composition, result)
    finally:
        composition.down()


@pytest.fixture(scope="session")
def keycloak_running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Started]:
    """EKO-1-12: the development profile after the live, ordered Keycloak bootstrap."""
    from tests.runtime.keycloak_client import prepare, run_bootstrap

    composition = new_composition(tmp_path_factory, "keycloak")
    try:
        prepare(composition)
        result = run_bootstrap(composition)
        yield Started(composition, result)
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


@pytest.fixture(scope="session")
def chromium_executable(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from tests.support.chromium import install_chromium

    return install_chromium(tmp_path_factory.mktemp("verified-chromium"))


def random_marker() -> str:
    return "marker-" + secrets.token_hex(6)


@pytest.fixture(scope="session")
def lab(tmp_path_factory: pytest.TempPathFactory) -> Iterator["Lab"]:
    """EKO-1-11: postgres and backend of the shipped image, with migrate runs on demand."""
    from tests.runtime.lab import Lab, PsqlSession, docker

    composition = new_composition(tmp_path_factory, "lab")
    monitor: PsqlSession | None = None
    started: Lab | None = None
    try:
        up = composition.compose(
            "up", "--build", "--wait", "--wait-timeout", str(UP_TIMEOUT_SECONDS), "backend",
            check=False, timeout=UP_TIMEOUT_SECONDS + 300,
        )  # fmt: skip
        if up.returncode != 0:
            logs = composition.compose("logs", "--tail", "40", check=False).stdout
            raise AssertionError(f"up exited {up.returncode}\n{up.stderr[-3000:]}\n{logs[-6000:]}")
        prober = f"{composition.project}-prober"
        composition.compose(
            "run", "-d", "--no-deps", "--name", prober, "--entrypoint", "sleep", "migrate",
            "infinity",
        )  # fmt: skip
        shipped = composition.inspect("backend")["Config"]["Image"]
        monitor = PsqlSession(composition, name="eko-test-monitor")
        workdir = tmp_path_factory.mktemp("lab-work")
        started = Lab(composition, workdir, shipped, prober, monitor)
        yield started
    finally:
        if monitor is not None:
            monitor.close()
        if started is not None:
            docker("rm", "-f", started.prober, check=False)
            for tag in started.images.values():
                docker("rmi", "-f", tag, check=False)
        composition.down()


@pytest.fixture(scope="session")
def backup_lab(tmp_path_factory: pytest.TempPathFactory) -> Iterator["BackupLab"]:
    """EKO-1-14: postgres, keycloak, migrate on demand and the destination double."""
    from tests.runtime.backup_lab import backup_lab_session

    yield from backup_lab_session(tmp_path_factory)


@pytest.fixture(autouse=True)
def no_scheduler_outlives_its_test(request: pytest.FixtureRequest) -> Iterator[None]:
    """R-03: the `backup` service a test starts (its real scheduler) is stopped after that test,
    so a session spanning 01:00 UTC never gets a real run in the middle of other tests."""
    yield
    if "backup_lab" in request.fixturenames:
        backup_lab: BackupLab = request.getfixturevalue("backup_lab")
        backup_lab.stop_scheduler()
        assert not backup_lab.scheduler_running(), "the backup scheduler is still running"
