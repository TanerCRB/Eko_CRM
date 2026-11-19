"""EKO-1-34 (#192): wait until the host's view of a composition's network has settled.

The bootstrap's last `compose restart proxy` gives the proxy a new host-side veth on the
composition's bridge. That veth's IPv6 link-local address leaves duplicate address detection
1-2 s later (K-01 record, run 44169988387: +0.97 to +1.97 s after the restart), and Chromium on
the host reads the new address as a network change: a navigation still being set up fails with
`net::ERR_NETWORK_CHANGED`. `settle_host_network` returns once every interface of the
composition's bridges (each bridge and each of its members) holds a link-local address that is no
longer tentative, so a browser login started afterwards does not overlap that change.

It reads kernel state only (sysfs and `/proc/net/if_inet6`) after two `docker network` queries.
It never navigates, never calls Playwright, catches nothing a browser raises and changes nothing
in the composition, the bootstrap or the proxy (ADR-0004 C33).

Where the bridges cannot be in this host's network namespace, the wait does not apply. That is
decided from an explicit engine fact only (`docker info` names Docker Desktop, or the engine is
Linux while this host is not), and the decision is written to the test output as a warning. On a
Linux engine on this host, a missing bridge, an empty bridge or an unreadable address table fails
with a named error, never as a silent pass.
"""

import errno
import logging
import subprocess
import sys
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.runtime.conftest import Composition

logger = logging.getLogger(__name__)

# Five times the slowest settle the K-01 record observed (1.97 s after the restart). The kernel's
# default detection (a random delay below router_solicitation_delay, 1 s, then one probe left
# unanswered for retrans_time, 1 s) ends within about 2 s; the rest is room for a loaded runner.
SETTLE_BOUND_SECONDS = 10.0
POLL_SECONDS = 0.05
SCOPE_LINK = 0x20
IFA_F_DADFAILED = 0x08
IFA_F_TENTATIVE = 0x40
PROJECT_LABEL = "com.docker.compose.project"
BRIDGE_NAME_OPTION = "com.docker.network.bridge.name"


class HostNetworkNotSettled(AssertionError):
    """The bridge interfaces still held a tentative or missing link-local address at the bound."""


class HostNetworkNotFound(AssertionError):
    """A Linux engine on this host, but the composition's bridge cannot be read here."""


class HostNetworkNotApplicable(UserWarning):
    """The engine's bridges live outside this host's namespace: the decision and its fact."""


@dataclass(frozen=True)
class Engine:
    applies: bool
    fact: str


@dataclass(frozen=True)
class Interface:
    name: str
    settled: bool
    state: str


@dataclass(frozen=True)
class Outcome:
    applies: bool
    detail: str
    waited_seconds: float
    interfaces: tuple[str, ...]


def docker_output(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    if result.returncode != 0:
        raise HostNetworkNotFound(
            f"EKO-1-34: `docker {' '.join(args[:2])}` exited {result.returncode}: "
            f"{result.stderr.strip()[-500:]}"
        )
    return result.stdout


def engine(info: str | None = None, platform: str = sys.platform) -> Engine:
    """Whether the engine's bridges are in this host's namespace, from `docker info` only."""
    if info is None:
        info = docker_output("info", "--format", "{{.OSType}}|{{.OperatingSystem}}")
    os_type, _, operating_system = info.strip().partition("|")
    if "Docker Desktop" in operating_system:
        return Engine(
            False,
            f"docker info reports OperatingSystem={operating_system!r}: the engine and its "
            "bridges run in Docker Desktop's virtual machine, not in this host's network "
            "namespace, so a browser here never sees their addresses",
        )
    if not platform.startswith("linux"):
        return Engine(
            False,
            f"docker info reports OSType={os_type!r} while this host is {platform!r}: a Linux "
            "engine's bridges cannot be in this host's network namespace",
        )
    return Engine(
        True, f"OSType={os_type!r}, OperatingSystem={operating_system!r}, host {platform}"
    )


def project_bridges(project: str) -> list[str]:
    """The host interface names of the bridges of the compose project's own networks."""
    ids = docker_output(
        "network", "ls", "--no-trunc", "--filter", f"label={PROJECT_LABEL}={project}",
        "--format", "{{.ID}}",
    ).split()  # fmt: skip
    if not ids:
        raise HostNetworkNotFound(f"EKO-1-34: no Docker network carries {PROJECT_LABEL}={project}")
    bridges = []
    for network_id in ids:
        described = docker_output(
            "network", "inspect", network_id, "--format",
            '{{.Driver}}|{{index .Options "' + BRIDGE_NAME_OPTION + '"}}',
        ).strip()  # fmt: skip
        driver, _, named = described.partition("|")
        if driver != "bridge":
            raise HostNetworkNotFound(
                f"EKO-1-34: network {network_id[:12]} of {project} uses driver {driver!r}, "
                "not a host bridge"
            )
        bridges.append(named if named and named != "<no value>" else f"br-{network_id[:12]}")
    return bridges


def link_local_flags(if_inet6: str) -> dict[int, list[int]]:
    """Interface index -> the flags of each of its link-scope addresses."""
    found: dict[int, list[int]] = {}
    for line in if_inet6.splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        index, scope, flags = int(fields[1], 16), int(fields[3], 16), int(fields[4], 16)
        if scope == SCOPE_LINK:
            found.setdefault(index, []).append(flags)
    return found


def read_device_file(path: Path) -> str | None:
    """A sysfs or procfs file of one interface; None while the device is (un)registering."""
    try:
        return path.read_text("ascii").strip()
    except OSError as error:
        # sysfs answers EINVAL or ENODEV, not ENOENT, for a veth that is being unregistered.
        if error.errno in (errno.ENOENT, errno.ENODEV, errno.EINVAL):
            return None
        raise


def interface_state(name: str, root: Path, addresses: dict[int, list[int]] | None) -> Interface:
    index = read_device_file(root / "sys/class/net" / name / "ifindex")
    if index is None:
        return Interface(name, False, "gone or not ready while being read")
    if addresses is None:
        return Interface(name, True, "IPv6 is not available in this host's kernel")
    switch = read_device_file(root / "proc/sys/net/ipv6/conf" / name / "disable_ipv6")
    if switch is None:
        return Interface(name, False, "no IPv6 configuration yet")
    if switch == "1":
        return Interface(name, True, "IPv6 disabled on the interface: no link-local will come")
    flags = addresses.get(int(index), [])
    if any(not value & (IFA_F_TENTATIVE | IFA_F_DADFAILED) for value in flags):
        return Interface(name, True, "link-local address settled")
    if not flags:
        return Interface(name, False, "no link-local address yet")
    return Interface(name, False, "link-local address " + ", ".join(f"{v:#04x}" for v in flags))


def network_state(bridges: list[str], root: Path) -> list[Interface]:
    """Every bridge and every member of it, read once from sysfs and the address table."""
    table = root / "proc/net/if_inet6"
    addresses: dict[int, list[int]] | None
    if table.is_file():
        addresses = link_local_flags(table.read_text("ascii"))
    elif not (root / "proc/sys/net/ipv6").exists():
        addresses = None
    else:
        raise HostNetworkNotFound(f"EKO-1-34: IPv6 is configured but {table} cannot be read")
    states = []
    for bridge in bridges:
        members = root / "sys/class/net" / bridge / "brif"
        if not members.is_dir():
            raise HostNetworkNotFound(
                f"EKO-1-34: bridge {bridge} is not in this host's network namespace although the "
                "engine is a Linux engine on this host; no veth to wait for was found"
            )
        names = sorted(entry.name for entry in members.iterdir())
        if not names:
            raise HostNetworkNotFound(f"EKO-1-34: bridge {bridge} has no member: no veth found")
        states += [interface_state(name, root, addresses) for name in [bridge, *names]]
    return states


def settle_host_network(
    composition: "Composition",
    *,
    bound: float = SETTLE_BOUND_SECONDS,
    root: Path = Path("/"),
    engine_fact: Engine | None = None,
    bridges: Callable[[str], list[str]] = project_bridges,
    clock: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Return once every interface of the composition's bridges holds a settled link-local
    address; raise `HostNetworkNotSettled`, naming the interfaces still pending, at `bound`."""
    fact = engine_fact if engine_fact is not None else engine()
    if not fact.applies:
        detail = f"EKO-1-34 host-network settle does not apply: {fact.fact}"
        warnings.warn(detail, HostNetworkNotApplicable, stacklevel=2)
        logger.warning("host-network settle does not apply to %s", composition.project)
        return Outcome(False, detail, 0.0, ())
    names = bridges(composition.project)
    started = clock()
    while True:
        states = network_state(names, root)
        pending = [state for state in states if not state.settled]
        waited = clock() - started
        if not pending:
            logger.info(
                "host network of %s settled after %.2f s (%d interfaces)",
                composition.project,
                waited,
                len(states),
            )
            return Outcome(True, fact.fact, waited, tuple(state.name for state in states))
        if waited >= bound:
            listed = "; ".join(f"{state.name}: {state.state}" for state in pending)
            raise HostNetworkNotSettled(
                f"EKO-1-34: the host's view of {composition.project}'s network did not settle "
                f"within {bound:g} s ({listed})"
            )
        pause(POLL_SECONDS)
