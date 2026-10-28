"""R-05 / ADR-0004 *HTTPS exposure*: plain HTTP redirects to the same URL over HTTPS, on the port
the HTTPS listener is actually published on (8443 in the development profile, not 443)."""

import pytest

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime

PATH = "/some/deep/link?tab=visits"


@pytest.mark.parametrize("host_variable", ["APP_HOST", "AUTH_HOST"])
def test_adr0004_http_redirect_targets_the_published_https_port(
    running: Started, host_variable: str
) -> None:
    env = running.composition.env
    host = env[host_variable]
    response = running.composition.through_proxy("http", PATH, host=host)
    assert response.status_code in (301, 308)
    assert response.headers["location"] == f"https://{host}:{env['PROXY_HTTPS_PORT']}{PATH}"
