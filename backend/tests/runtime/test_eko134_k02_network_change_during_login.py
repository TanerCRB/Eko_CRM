"""EKO-1-34 (#192) K-02: the identified change, reproduced on demand during the login.

The K-01 record names the cause: a new host-side veth on the test composition's own bridge
(created by the bootstrap's last `compose restart proxy`) gets its IPv6 link-local address 1-2 s
later, and a document navigation of `browser_login`'s first redirect chain that is still being
set up then fails with `net::ERR_NETWORK_CHANGED`. Left to chance, that overlap happened in 5 of
40 test runs. Here it is made certain:

- the hold: the composition's own proxy is paused, so the login's first connection stays in its
  TLS handshake (a connection still being set up) until the hold ends;
- the interference: a new veth on the same bridge, from a throwaway container of the proxy's own
  image (already present, `--pull never`), attached to the composition's own network only;
- the hold ends once the new veth has left duplicate address detection and either the browser
  reported the request failed or a grace of a few seconds passed.

The pre-fix harness starts the login right after the interference: the change lands while the
handshake is pending, and the login fails with `ERR_NETWORK_CHANGED`. The fixed harness puts the
fix (`settle_host_network`) at the same place the two K-06 tests do; the login then completes.
The contrast leaves the interference out and changes nothing else; the login completes.

Each test asserts K-02's three edges in its clean-up, also when its body failed: no image was
pulled or built, no other compose project's containers or networks changed, and nothing the
interference created (container, volume, bridge member, paused proxy) remains.

Linux engine on this host only: on Docker Desktop, or with a Linux engine and a non-Linux host,
the bridge is not in the browser's namespace and the module is skipped with the engine fact named.
Synthetic accounts only.
"""

import logging
import subprocess
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Request, sync_playwright

from tests.runtime import eko134_host_network as host
from tests.runtime import eko201_login as app
from tests.runtime.conftest import UP_TIMEOUT_SECONDS, Composition, new_composition
from tests.runtime.keycloak_client import build_keycloak, run_bootstrap

pytestmark = pytest.mark.runtime

logger = logging.getLogger(__name__)

HOST_ROOT = Path("/")
INTERFERENCE_LABEL = "eko134.interference"
# How long the hold waits for the login's first request, and for the new veth to settle.
HOLD_BOUND_SECONDS = 10.0
# Chromium aborted 11-17 ms after the address in the K-01 record; the hold stays this long after
# the change, unless the browser reports the failure first.
HOLD_GRACE_SECONDS = 3.0
# The newest veth of the churn must stay younger than the shortest detection (about 1 s).
CHURN_MAX_GAP_SECONDS = 0.9


@pytest.fixture(scope="module")
def linux_engine() -> host.Engine:
    fact = host.engine()
    if not fact.applies:
        pytest.skip(f"EKO-1-34 K-02 reproducer is not runnable on this engine: {fact.fact}")
    return fact


@pytest.fixture(scope="module")
def bootstrapped(
    linux_engine: host.Engine, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Composition]:
    """A composition brought up the way the two K-06 tests bring up `fresh`."""
    composition = new_composition(tmp_path_factory, "eko134")
    try:
        build_keycloak(composition)
        up = composition.compose(
            "up", "--build", "--wait", "--wait-timeout", str(UP_TIMEOUT_SECONDS), "proxy",
            check=False, timeout=UP_TIMEOUT_SECONDS + 300,
        )  # fmt: skip
        assert up.returncode == 0, up.stderr[-6000:]
        run_bootstrap(composition)
        yield composition
    finally:
        composition.down()


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    if check and result.returncode != 0:
        raise AssertionError(f"docker {' '.join(args[:2])} exited {result.returncode}")
    return result.stdout


def bridge_members(bridges: list[str]) -> frozenset[str]:
    found: set[str] = set()
    for bridge in bridges:
        members = HOST_ROOT / "sys/class/net" / bridge / "brif"
        found |= {entry.name for entry in members.iterdir()}
    return frozenset(found)


def all_settled(bridges: list[str]) -> bool:
    return all(state.settled for state in host.network_state(bridges, HOST_ROOT))


@dataclass(frozen=True)
class Snapshot:
    images: frozenset[str]
    other_projects: frozenset[str]
    volumes: frozenset[str]
    members: frozenset[str]
    interference: frozenset[str]
    proxy_paused: bool


def labelled(kind: str, project: str) -> frozenset[str]:
    """`<project> <id>` of every container or network of a compose project other than this one."""
    listing = docker(
        kind, "ls", *(["-a"] if kind == "container" else []), "--no-trunc", "--format",
        '{{.ID}}|{{.Label "com.docker.compose.project"}}',
    )  # fmt: skip
    rows = (line.partition("|") for line in listing.splitlines() if line)
    return frozenset(
        f"{kind} {owner} {ident}" for ident, _, owner in rows if owner not in ("", project)
    )


def snapshot(composition: Composition, bridges: list[str], proxy: str) -> Snapshot:
    return Snapshot(
        images=frozenset(docker("image", "ls", "-aq", "--no-trunc").split()),
        other_projects=labelled("container", composition.project)
        | labelled("network", composition.project),
        volumes=frozenset(docker("volume", "ls", "-q").split()),
        members=bridge_members(bridges),
        interference=frozenset(
            docker("ps", "-aq", "--no-trunc", "--filter", f"label={INTERFERENCE_LABEL}").split()
        ),
        proxy_paused=docker("inspect", "-f", "{{.State.Paused}}", proxy).strip() == "true",
    )


def edge_findings(before: Snapshot, after: Snapshot) -> list[str]:
    findings = []
    if after.images != before.images:
        findings.append(f"(1) local image ids changed: {sorted(after.images ^ before.images)}")
    if after.other_projects != before.other_projects:
        changed = sorted(after.other_projects ^ before.other_projects)
        findings.append(f"(2) another compose project's containers or networks changed: {changed}")
    if after.interference:
        findings.append(f"(3) interference containers remain: {sorted(after.interference)}")
    if after.volumes != before.volumes:
        findings.append(f"(3) volumes differ: {sorted(after.volumes ^ before.volumes)}")
    if after.members != before.members:
        findings.append(f"(3) bridge members differ: {sorted(after.members ^ before.members)}")
    if after.proxy_paused:
        findings.append("(3) the composition's proxy is still paused")
    return findings


class Interference:
    """The hold (the paused proxy) and the new veths, all on the composition's own network."""

    def __init__(self, composition: Composition) -> None:
        self.composition = composition
        self.proxy = composition.container_id("proxy")
        self.image = docker("inspect", "-f", "{{.Image}}", self.proxy).strip()
        networks = docker(
            "network", "ls", "--no-trunc", "--format", "{{.ID}}",
            "--filter", f"label=com.docker.compose.project={composition.project}",
        ).split()  # fmt: skip
        assert len(networks) == 1, f"expected the composition's one network, got {networks}"
        self.network = networks[0]
        self.bridges = host.project_bridges(composition.project)
        self.created: list[str] = []

    def hold(self) -> None:
        docker("pause", self.proxy)

    def release(self) -> None:
        if docker("inspect", "-f", "{{.State.Paused}}", self.proxy).strip() == "true":
            docker("unpause", self.proxy)

    def new_veth(self, name: str) -> str:
        """A throwaway container on the composition's network: one new host-side veth."""
        before = bridge_members(self.bridges)
        container = f"{self.composition.project}-eko134-{name}"
        docker(
            "run", "-d", "--name", container, "--label", f"{INTERFERENCE_LABEL}={name}",
            "--network", self.network, "--pull", "never", "--entrypoint", "sleep", self.image,
            "600",
        )  # fmt: skip
        self.created.append(container)
        added = bridge_members(self.bridges) - before
        assert len(added) == 1, f"the interference added {sorted(added)} to the bridge"
        return next(iter(added))

    def clean_up(self) -> None:
        self.release()
        for container in self.created:
            docker("rm", "-f", "-v", container, check=False)


@contextmanager
def guarded(composition: Composition) -> Iterator[Interference]:
    """K-02 edges, asserted after the clean-up even when the body failed."""
    interference = Interference(composition)
    before = snapshot(composition, interference.bridges, interference.proxy)
    try:
        yield interference
    finally:
        interference.clean_up()
        findings = edge_findings(
            before, snapshot(composition, interference.bridges, interference.proxy)
        )
        if findings:
            raise AssertionError("EKO-1-34 K-02 interference edges: " + "; ".join(findings))


class HeldLogin:
    """Ends the hold once the login's first request is out, the bridge has settled, and either
    the browser reported a failed request or the grace passed. Never touches the page."""

    def __init__(self, interference: Interference, page: Page) -> None:
        self.interference = interference
        self.in_flight = threading.Event()
        self.failed = threading.Event()
        self.settled_at_flight: bool | None = None
        self.members_at_flight: frozenset[str] = frozenset()
        page.on("request", self._request)
        page.on("requestfailed", lambda request: self.failed.set())

    def _request(self, request: Request) -> None:
        if request.resource_type == "document" and not self.in_flight.is_set():
            self.settled_at_flight = all_settled(self.interference.bridges)
            self.members_at_flight = bridge_members(self.interference.bridges)
            self.in_flight.set()

    def _run(self) -> None:
        try:
            if not self.in_flight.wait(HOLD_BOUND_SECONDS):
                raise AssertionError("EKO-1-34 K-02 hold: the login's first request never started")
            deadline = time.monotonic() + HOLD_BOUND_SECONDS
            while not all_settled(self.interference.bridges):
                if time.monotonic() >= deadline:
                    raise AssertionError("EKO-1-34 K-02 hold: the bridge did not settle")
                time.sleep(host.POLL_SECONDS)
            self.failed.wait(HOLD_GRACE_SECONDS)
        finally:
            self.interference.release()

    @contextmanager
    def running(self) -> Iterator[None]:
        """The release runs beside the login; its own failure is raised here when it ends."""
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="eko134-hold") as pool:
            released = pool.submit(self._run)
            try:
                yield
            finally:
                logger.info(
                    "hold: settled at first request %s, members %s",
                    self.settled_at_flight,
                    sorted(self.members_at_flight),
                )
                released.result(timeout=HOLD_BOUND_SECONDS * 2 + HOLD_GRACE_SECONDS)


@contextmanager
def browser_page(composition: Composition, chromium_executable: Path) -> Iterator[Page]:
    """Launched as the two K-06 tests launch theirs."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium_executable),
            headless=True,
            args=[app.browser_host_rules(composition)],
        )
        try:
            context = browser.new_context(ignore_https_errors=True)
            yield context.new_page()
        finally:
            browser.close()


def test_eko134_k02_new_veth_during_login_redirect_fails_at_the_pre_fix_harness(
    bootstrapped: Composition, chromium_executable: Path
) -> None:
    host.settle_host_network(bootstrapped)
    username, password = app.provision_browser_account(bootstrapped, "login")
    with guarded(bootstrapped) as interference:
        with browser_page(bootstrapped, chromium_executable) as page:
            held = HeldLogin(interference, page)
            interference.hold()
            veth = interference.new_veth("prefix")
            with held.running():
                with pytest.raises(PlaywrightError) as raised:
                    app.browser_login(page, bootstrapped, username, password)
    assert "net::ERR_NETWORK_CHANGED" in str(raised.value), str(raised.value)
    assert veth in held.members_at_flight
    assert held.settled_at_flight is False, "the change had settled before the login started"


def test_eko134_k02_new_veth_before_login_passes_at_the_fixed_harness(
    bootstrapped: Composition, chromium_executable: Path
) -> None:
    host.settle_host_network(bootstrapped)
    username, password = app.provision_browser_account(bootstrapped, "logout")
    with guarded(bootstrapped) as interference:
        with browser_page(bootstrapped, chromium_executable) as page:
            held = HeldLogin(interference, page)
            interference.hold()
            veth = interference.new_veth("fixed")
            settled = host.settle_host_network(bootstrapped)
            with held.running():
                app.browser_login(page, bootstrapped, username, password)
            assert page.url == app.app_origin(bootstrapped) + "/", page.url
    assert settled.applies is True
    assert veth in settled.interfaces
    assert veth in held.members_at_flight
    assert held.settled_at_flight is True


def test_eko134_k02_contrast_without_the_interference_passes_at_the_pre_fix_harness(
    bootstrapped: Composition, chromium_executable: Path
) -> None:
    host.settle_host_network(bootstrapped)
    username, password = app.provision_browser_account(bootstrapped, "pages")
    with guarded(bootstrapped) as interference:
        with browser_page(bootstrapped, chromium_executable) as page:
            held = HeldLogin(interference, page)
            interference.hold()
            with held.running():
                app.browser_login(page, bootstrapped, username, password)
            assert page.url == app.app_origin(bootstrapped) + "/", page.url
    assert held.settled_at_flight is True


def test_eko134_k02_continuous_interference_fails_the_wait_by_name_within_its_bound(
    bootstrapped: Composition,
) -> None:
    host.settle_host_network(bootstrapped)
    with guarded(bootstrapped) as interference:
        for number in range(3):
            interference.new_veth(f"churn{number}")
        containers = list(interference.created)
        stop = threading.Event()
        gaps: list[float] = []

        def churn() -> None:
            last = time.monotonic()
            while not stop.is_set():
                for container in containers:
                    docker("network", "disconnect", interference.network, container)
                    docker("network", "connect", interference.network, container)
                    now = time.monotonic()
                    gaps.append(now - last)
                    last = now

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="eko134-churn") as pool:
            churning = pool.submit(churn)
            started = time.monotonic()
            try:
                with pytest.raises(host.HostNetworkNotSettled) as raised:
                    host.settle_host_network(bootstrapped)
                elapsed = time.monotonic() - started
            finally:
                stop.set()
                churning.result(timeout=60)
    assert max(gaps) < CHURN_MAX_GAP_SECONDS, f"the churn paused {max(gaps):.2f} s: not continuous"
    assert "did not settle within 10 s" in str(raised.value)
    assert host.SETTLE_BOUND_SECONDS <= elapsed < host.SETTLE_BOUND_SECONDS + 5, elapsed
