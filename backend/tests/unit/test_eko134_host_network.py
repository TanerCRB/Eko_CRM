"""EKO-1-34 (#192) K-02 edges: the settle wait is bounded, fails by name, and decides "does not
apply" only from an explicit engine fact.

The wait reads a host's sysfs and `/proc/net/if_inet6`; here both are a fake tree under
`tmp_path`, and time is a fake clock advanced only by the wait's own pause, so a hang would show
as a test that never ends and a silent pass as a missing exception.
"""

import errno
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.runtime import eko134_host_network as host
from tests.runtime.conftest import Composition

PROJECT = "ekort-fresh-1a2b3c4d"
BRIDGE = "br-708d3e49f43a"
COMPOSITION = Composition(PROJECT, Path("never-read.env"))
LINUX = host.Engine(True, "OSType='linux', OperatingSystem='Ubuntu 26.04 LTS', host linux")


class Clock:
    def __init__(self, on_pause: Callable[[int], None] | None = None) -> None:
        self.now = 100.0
        self.pauses = 0
        self.on_pause = on_pause

    def __call__(self) -> float:
        return self.now

    def pause(self, seconds: float) -> None:
        self.pauses += 1
        self.now += seconds
        if self.on_pause is not None:
            self.on_pause(self.pauses)


class Tree:
    """A host's sysfs and procfs as far as the wait reads them."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.addresses: dict[str, tuple[int, int]] = {}
        self.next_index = 10
        (root / "proc" / "net").mkdir(parents=True)
        self.write_table()

    def interface(self, name: str, *, bridge: str | None = None, disable_ipv6: str = "0") -> None:
        net = self.root / "sys" / "class" / "net" / name
        net.mkdir(parents=True)
        (net / "ifindex").write_text(f"{self.next_index}\n", encoding="ascii")
        self.next_index += 1
        conf = self.root / "proc" / "sys" / "net" / "ipv6" / "conf" / name
        conf.mkdir(parents=True)
        (conf / "disable_ipv6").write_text(disable_ipv6 + "\n", encoding="ascii")
        if bridge is None:
            (net / "brif").mkdir()
        else:
            (self.root / "sys" / "class" / "net" / bridge / "brif" / name).write_text("")

    def link_local(self, name: str, flags: int) -> None:
        index = int((self.root / "sys/class/net" / name / "ifindex").read_text().strip())
        self.addresses[name] = (index, flags)
        self.write_table()

    def write_table(self) -> None:
        lines = ["00000000000000000000000000000001 01 80 10 80       lo"]
        for name, (index, flags) in self.addresses.items():
            lines.append(f"fe80000000000000d4f7b4fffe19c148 {index:02x} 40 20 {flags:02x} {name}")
        (self.root / "proc" / "net" / "if_inet6").write_text("\n".join(lines) + "\n")


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    built = Tree(tmp_path)
    built.interface(BRIDGE)
    built.link_local(BRIDGE, 0x80)
    built.interface("veth70e9731", bridge=BRIDGE)
    return built


def settle(tree: Tree, clock: Clock, engine: host.Engine = LINUX) -> host.Outcome:
    return host.settle_host_network(
        COMPOSITION,
        root=tree.root,
        engine_fact=engine,
        bridges=lambda project: [BRIDGE] if project == PROJECT else [],
        clock=clock,
        pause=clock.pause,
    )


def test_eko134_k02_the_wait_returns_once_the_new_veth_leaves_duplicate_address_detection(
    tree: Tree,
) -> None:
    tree.link_local("veth70e9731", host.IFA_F_TENTATIVE)

    def detection_ends(pauses: int) -> None:
        if pauses == 30:
            tree.link_local("veth70e9731", 0x00)

    clock = Clock(detection_ends)
    outcome = settle(tree, clock)
    assert outcome.applies is True
    assert clock.pauses == 30
    assert outcome.waited_seconds == pytest.approx(30 * host.POLL_SECONDS)
    assert outcome.interfaces == (BRIDGE, "veth70e9731")


def test_eko134_k02_a_veth_with_no_link_local_yet_is_waited_for(tree: Tree) -> None:
    def address_arrives(pauses: int) -> None:
        if pauses == 5:
            tree.link_local("veth70e9731", host.IFA_F_TENTATIVE)
        if pauses == 12:
            tree.link_local("veth70e9731", 0x00)

    clock = Clock(address_arrives)
    assert settle(tree, clock).applies is True
    assert clock.pauses == 12


def test_eko134_k02_continuous_interference_fails_the_wait_by_name_at_its_bound(
    tree: Tree,
) -> None:
    tree.link_local("veth70e9731", host.IFA_F_TENTATIVE)

    def a_new_veth_every_half_second(pauses: int) -> None:
        if pauses % 10 == 0:
            name = f"vethchurn{pauses}"
            tree.interface(name, bridge=BRIDGE)
            tree.link_local(name, host.IFA_F_TENTATIVE)

    clock = Clock(a_new_veth_every_half_second)
    with pytest.raises(host.HostNetworkNotSettled) as raised:
        settle(tree, clock)
    assert clock.now - 100.0 == pytest.approx(host.SETTLE_BOUND_SECONDS, abs=host.POLL_SECONDS)
    message = str(raised.value)
    assert message.startswith("EKO-1-34: the host's view of ekort-fresh-1a2b3c4d's network")
    assert "did not settle within 10 s" in message
    assert "veth70e9731: link-local address 0x40" in message


def test_eko134_k02_a_failed_duplicate_address_detection_never_counts_as_settled(
    tree: Tree,
) -> None:
    tree.link_local("veth70e9731", host.IFA_F_TENTATIVE | host.IFA_F_DADFAILED)
    with pytest.raises(host.HostNetworkNotSettled, match="veth70e9731: link-local address 0x48"):
        settle(tree, Clock())


def test_eko134_k02_the_bridge_itself_is_waited_for_too(tree: Tree) -> None:
    tree.link_local("veth70e9731", 0x00)
    tree.link_local(BRIDGE, host.IFA_F_TENTATIVE)
    with pytest.raises(host.HostNetworkNotSettled, match=f"{BRIDGE}: link-local address 0x40"):
        settle(tree, Clock())


def test_eko134_k02_an_interface_with_ipv6_disabled_expects_no_link_local(tree: Tree) -> None:
    tree.interface("vethnoipv6", bridge=BRIDGE, disable_ipv6="1")
    tree.link_local("veth70e9731", 0x00)
    clock = Clock()
    assert settle(tree, clock).interfaces == (BRIDGE, "veth70e9731", "vethnoipv6")
    assert clock.pauses == 0


def test_eko134_k02_a_kernel_without_ipv6_has_nothing_to_wait_for(tmp_path: Path) -> None:
    net = tmp_path / "sys" / "class" / "net"
    (net / BRIDGE / "brif").mkdir(parents=True)
    (net / BRIDGE / "ifindex").write_text("4\n")
    (net / BRIDGE / "brif" / "veth1").write_text("")
    (net / "veth1").mkdir()
    (net / "veth1" / "ifindex").write_text("5\n")
    clock = Clock()
    outcome = host.settle_host_network(
        COMPOSITION,
        root=tmp_path,
        engine_fact=LINUX,
        bridges=lambda project: [BRIDGE],
        clock=clock,
        pause=clock.pause,
    )
    assert outcome.interfaces == (BRIDGE, "veth1")
    assert clock.pauses == 0


def test_eko134_k02_an_unreadable_address_table_fails_by_name(tree: Tree) -> None:
    (tree.root / "proc" / "net" / "if_inet6").unlink()
    with pytest.raises(host.HostNetworkNotFound, match="if_inet6 cannot be read"):
        settle(tree, Clock())


def test_eko134_k02_a_linux_engine_whose_bridge_is_not_here_fails_by_name(tree: Tree) -> None:
    with pytest.raises(host.HostNetworkNotFound, match="no veth to wait for was found"):
        host.settle_host_network(
            COMPOSITION,
            root=tree.root,
            engine_fact=LINUX,
            bridges=lambda project: ["br-000000000000"],
            clock=Clock(),
            pause=Clock().pause,
        )


def test_eko134_k02_a_bridge_without_a_member_fails_by_name(tmp_path: Path) -> None:
    tree = Tree(tmp_path)
    tree.interface(BRIDGE)
    with pytest.raises(host.HostNetworkNotFound, match=f"bridge {BRIDGE} has no member"):
        settle(tree, Clock())


def test_eko134_k02_docker_desktop_does_not_apply_and_the_test_output_says_why(
    tree: Tree,
) -> None:
    fact = host.engine("linux|Docker Desktop", platform="win32")
    assert fact.applies is False
    assert "OperatingSystem='Docker Desktop'" in fact.fact

    def no_bridge_query(project: str) -> list[str]:
        raise AssertionError("an engine that does not apply was queried for bridges")

    with pytest.warns(host.HostNetworkNotApplicable, match="Docker Desktop's virtual machine"):
        outcome = host.settle_host_network(
            COMPOSITION,
            root=tree.root,
            engine_fact=fact,
            bridges=no_bridge_query,
            clock=Clock(),
            pause=Clock().pause,
        )
    assert outcome.applies is False
    assert outcome.detail.startswith("EKO-1-34 host-network settle does not apply: docker info")


def test_eko134_k02_docker_desktop_on_linux_does_not_apply_either() -> None:
    fact = host.engine("linux|Docker Desktop", platform="linux")
    assert fact.applies is False


def test_eko134_k02_a_linux_engine_on_another_host_os_does_not_apply() -> None:
    fact = host.engine("linux|Ubuntu 26.04 LTS", platform="darwin")
    assert fact.applies is False
    assert "OSType='linux' while this host is 'darwin'" in fact.fact


def test_eko134_k02_a_linux_engine_on_a_linux_host_applies() -> None:
    fact = host.engine("linux|Ubuntu 26.04 LTS\n", platform="linux")
    assert fact.applies is True
    assert "OperatingSystem='Ubuntu 26.04 LTS'" in fact.fact


def test_eko134_k02_a_veth_removed_while_it_is_read_is_waited_for_not_an_error(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seen live under the churn: sysfs answers EINVAL for a veth that is being unregistered.
    tree.interface("vethdying", bridge=BRIDGE)
    tree.link_local("veth70e9731", 0x00)
    dying = tree.root / "sys" / "class" / "net" / "vethdying" / "ifindex"
    original = Path.read_text

    def read_text(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if path == dying:
            raise OSError(errno.EINVAL, "Invalid argument")
        return original(path, encoding, errors)

    monkeypatch.setattr(Path, "read_text", read_text)

    def unregistered(pauses: int) -> None:
        if pauses == 3:
            (tree.root / "sys" / "class" / "net" / BRIDGE / "brif" / "vethdying").unlink()

    clock = Clock(unregistered)
    assert settle(tree, clock).interfaces == (BRIDGE, "veth70e9731")
    assert clock.pauses == 3
