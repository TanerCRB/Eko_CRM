"""ADR-0004 *HTTPS exposure* on the running `proxy` (QA, EKO-1-06; not one of K-01..K-07).

Before this file these rules were probed by hand only:

- the public Keycloak listener forwards only the application realm (`eko`) and static resources;
  the same request for another realm is refused by `proxy` (403), not by Keycloak;
- the account console is refused on the public listener;
- the admin listener forwards from the company network and refuses (403) any other source; the
  contrast is a second `proxy`, identical except for COMPANY_NETWORK_CIDRS, with nothing behind it,
  so a request it forwarded would be a 502;
- plain HTTP on the application host redirects to HTTPS.
"""

import time

import httpx
import pytest

from tests.runtime.conftest import Composition, Started, read_env, write_env

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
    # EKO-1-12 (ADR-0004 addendum): the listener answers only behind its gate marker, and the
    # bootstrap cannot open it in this environment — its own gate check arrives from inside the
    # composition network, which the foreign CIDR set above refuses (TEST-NET-1 holds no Docker
    # or host address). This contrast therefore opens the marker the bootstrap would write,
    # with nothing running behind the listener at all.
    fresh.compose("exec", "-T", "proxy", "touch", "/data/admin-open")
    fresh.compose("restart", "proxy", timeout=120)
    refused: httpx.Response | None = None
    deadline = time.monotonic() + 60
    while refused is None and time.monotonic() < deadline:
        try:
            refused = fresh.through_proxy("admin", DISCOVERY.format(realm="master"))
        except (httpx.HTTPError, OSError):
            time.sleep(1)
    assert refused is not None, "the admin listener never became reachable behind its marker"
    # 403 is proxy's refusal; a forwarded request would find no keycloak and be a 502.
    assert refused.status_code == 403


def test_adr0004_plain_http_redirects_to_https(running: Started) -> None:
    response = running.composition.through_proxy("http", "/")
    assert response.status_code in (301, 302, 307, 308)
    assert response.headers["location"].startswith("https://")
