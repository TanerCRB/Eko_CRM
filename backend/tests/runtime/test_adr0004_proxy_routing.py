"""ADR-0004 *HTTPS exposure* on the running `proxy` (QA, EKO-1-06; not one of K-01..K-07).

Before this file these rules were probed by hand only:

- the public Keycloak listener forwards only the application realm (`eko`) and static resources;
  the same request for another realm is refused by `proxy` (403), not by Keycloak;
- the account console is refused on the public listener;
- the admin listener forwards from the company network and refuses (403) any other source; the
  contrast is the same `proxy` with COMPANY_NETWORK_CIDRS pointed at TEST-NET-1 and an
  un-bootstrapped Keycloak behind the listener, so a request the refusal did not block would
  be Keycloak's own status (503 "Bootstrap in progress", later 200) — never a proxy 403;
- plain HTTP on the application host redirects to HTTPS.

Hardening 2026-11-11 (CI runs 42897088542 and 42711869762: this test was red in BOTH runtime
jobs on this branch, reproduced red locally before the change): the EKO-1-12 boot-identity
correction (ADR-0004-C33, addendum 2026-11-10) made a gate marker only open while its CONTENT
names the current Keycloak boot, but this file's marker phase still blind-touched an empty
marker — an existence-only marker is no longer a gate, so the listener never bound and the
poll failed on "never became reachable", not on anything about the network rule. The phase now
starts Keycloak (its entrypoint wrapper rotates the boot token as the first act of every
start — no bootstrap needed, and none can run here: the script's own gate check arrives from
inside the composition network, which the foreign CIDR set refuses) and writes the marker
through `write_gate_marker`, the same primitive `open_gate` uses. The restart is followed by
the eko112 family's proven waits (`wait_for_proxy_running`, `wait_for_serving`) replacing the
old one-shot-after-restart probe — the same finding F-04 race class, which here would have
turned the refusal poll into a 60 s timeout.
"""

import time

import pytest

from tests.runtime.conftest import Composition, Started, read_env, write_env
from tests.runtime.keycloak_client import boot_identity, write_gate_marker
from tests.runtime.test_eko112_k02_marker_boot_binding import wait_for_proxy_running
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import wait_for_serving

pytestmark = pytest.mark.runtime

DISCOVERY = "/realms/{realm}/.well-known/openid-configuration"
# TEST-NET-1 (RFC 5737): no Docker network or host source address is ever in it.
FOREIGN_NETWORK = "192.0.2.0/24"


def keycloak_bootstrapped(started: Started, seconds: int = 180) -> None:
    """`up --wait` can report keycloak healthy while it still answers 503 "Bootstrap in progress"
    (QA finding F-01: its healthcheck matches a nested "UP"); wait for the real answer."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if (
            started.composition.through_proxy("admin", DISCOVERY.format(realm="master")).status_code
            != 503
        ):
            return
        time.sleep(2)
    raise AssertionError("keycloak still bootstrapping")


def test_adr0004_auth_listener_forwards_the_application_realm_only(running: Started) -> None:
    keycloak_bootstrapped(running)
    composition = running.composition
    application = composition.through_proxy("auth", DISCOVERY.format(realm="eko"))
    # Forwarded: Keycloak answers (the realm is created by EKO-1-12, so 404 is Keycloak's own).
    assert application.status_code != 403
    assert application.status_code < 500
    other = composition.through_proxy("auth", DISCOVERY.format(realm="master"))
    assert other.status_code == 403
    assert "issuer" not in other.text


@pytest.mark.parametrize("path", ["/admin/master/console/", "/realms/eko/account", "/metrics"])
def test_adr0004_auth_listener_refuses_paths_outside_the_allowlist(
    running: Started, path: str
) -> None:
    assert running.composition.through_proxy("auth", path).status_code == 403


def test_adr0004_admin_listener_forwards_from_the_company_network(running: Started) -> None:
    keycloak_bootstrapped(running)
    response = running.composition.through_proxy("admin", DISCOVERY.format(realm="master"))
    assert response.status_code == 200
    assert "issuer" in response.text


def test_adr0004_admin_listener_refuses_a_source_outside_the_company_network(
    fresh: Composition,
) -> None:
    values = read_env(fresh.env_file)
    values["COMPANY_NETWORK_CIDRS"] = FOREIGN_NETWORK
    write_env(fresh.env_file, values)
    fresh.compose("up", "-d", "--build", "--no-deps", "--wait", "proxy", timeout=600)
    # Start Keycloak so a boot token exists: the entrypoint wrapper rotates it as the FIRST
    # act of the start, before kc.sh, and `--wait` returns only past the server's own health
    # gate, so a single read here names a rotation the health chain already proves. No
    # bootstrap: its gate check would arrive from inside the composition network, which the
    # foreign CIDR set above refuses (TEST-NET-1 holds no Docker or host address), and none
    # of the routing contrast needs verified providers — only an open gate the entrypoint
    # accepts, written exactly the way `open_gate` writes one.
    fresh.compose(
        "up", "-d", "--wait", "--wait-timeout", "600", "keycloak", timeout=700
    )  # fmt: skip
    identity = boot_identity(fresh)
    assert identity, (
        "the proxy cannot observe a boot token after a started Keycloak: the marker below "
        "could not name a current boot"
    )
    write_gate_marker(fresh, "admin", identity)
    fresh.compose("restart", "proxy", timeout=120)
    # The finding F-04 wait pattern every eko112 sibling carries: `compose restart` returns
    # at container start, not at Caddy bind. First the container state (budget: the same
    # 120 s `wait_for_proxy_running` proved on these runners), then the listener's first
    # real HTTP answer (budget: `wait_for_serving`'s 90 s proven ceiling — it replaced this
    # test's own one-shot 60 s window). The status is then the bound configuration's reply,
    # not the bind window's silence.
    wait_for_proxy_running(fresh)
    refused_status = wait_for_serving(fresh, "admin")
    # 403 is proxy's refusal; a request the network matcher let through would reach the
    # un-bootstrapped Keycloak behind it — 503 until its internal bootstrap completes, 200
    # after — and the 403 assertion below turns that into the same red.
    assert refused_status == 403, (
        f"the admin listener answered {refused_status} to a source outside the company "
        "network; 403 is the only proxy-side refusal status (a forwarded request carries "
        "Keycloak's own 503/200)"
    )


def test_adr0004_plain_http_redirects_to_https(running: Started) -> None:
    response = running.composition.through_proxy("http", "/")
    assert response.status_code in (301, 302, 307, 308)
    assert response.headers["location"].startswith("https://")
