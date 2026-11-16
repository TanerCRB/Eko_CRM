"""EKO-1-13 K-02: `proxy` writes exactly one access line per request on every listener, holding
exactly C4's keys, the path without its query, and no cookie or header value other than the host
name, plus at most one error line under the same rule when its upstream fails (ADR-0005-C4;
addendum of 2026-11-02, Q-3 A).

Each request carries a marker in its query string, a marker cookie and a marker in another
header, and a path of its own, which is how its line is found. The key sets come from
docs/operations/log-format.md. Contrast: the same check on Caddy's default access-log line (the
field restriction removed) fails, since that line carries the full URI and the headers.
"""

import json
import secrets
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx
import pytest

from tests.runtime.conftest import Started
from tests.runtime.eko113 import Window, window
from tests.runtime.lab import docker
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
QUERY_MARKER = f"marker-q-{TOKEN}"
COOKIE_MARKER = f"marker-c-{TOKEN}"
HEADER_MARKER = f"marker-h-{TOKEN}"
FORWARDED_MARKER = "203.0.113.77"
NON_ASCII = f"Zażółć-{TOKEN}"
MARKERS = (QUERY_MARKER, COOKIE_MARKER, HEADER_MARKER, NON_ASCII, FORWARDED_MARKER)


def unique(label: str) -> str:
    return f"eko113-{label}-{secrets.token_hex(4)}"


def send(
    started: Started,
    listener: str,
    path: str,
    query: str | None = f"q={QUERY_MARKER}&n={quote(NON_ASCII)}",
    cookie: bool = True,
    host: str | None = None,
) -> httpx.Response:
    headers = {"X-Probe": HEADER_MARKER, "X-Forwarded-For": FORWARDED_MARKER}
    if cookie:
        headers["Cookie"] = f"sid={COOKIE_MARKER}"
    target = path if query is None else f"{path}?{query}"
    return started.composition.through_proxy(listener, target, host=host, headers=headers)


@pytest.fixture
def proxy_log(running: Started) -> Iterator[Window]:
    yield window(running.composition, "proxy")


def lines_for(text: str, path_part: str) -> tuple[list[dict[str, Any]], list[str]]:
    objects, others = ll.json_lines(text)
    mine = [o for o in objects if path_part in str(ll.flatten(o).get("request.uri", ""))]
    return mine, others


def access_problems(text: str, path_part: str) -> list[str]:
    mine, others = lines_for(text, path_part)
    access = [o for o in mine if "size" in o]
    problems = [f"not JSON: {line[:200]!r}" for line in others]
    if len(access) != 1:
        problems.append(f"{len(access)} access lines for {path_part}: {mine}")
    for line in access:
        problems += ll.proxy_line_problems(line, "proxy.access")
        if ll.flatten(line).get("request.client_ip") == FORWARDED_MARKER:
            problems.append("X-Forwarded-For became client_ip")
    problems += [f"marker {m}" for m in ll.leaks(text, *MARKERS)]
    return problems


LISTENER_CASES = {
    # listener -> (path, expected status)
    "app": ("/{u}", 200),
    "auth": ("/resources/{u}", 404),
    "admin": ("/{u}", 404),
    "http": ("/{u}", 308),
}


@pytest.mark.parametrize("listener", sorted(LISTENER_CASES))
def test_adr0005_c4_proxy_access_log(running: Started, proxy_log: Window, listener: str) -> None:
    template, status = LISTENER_CASES[listener]
    path = template.format(u=unique(listener))
    response = send(running, listener, path)
    if listener != "admin":
        assert response.status_code == status, response.status_code
    if listener == "http":
        # The redirect's Location carries the query: it must not be logged.
        assert QUERY_MARKER in response.headers["location"]
    assert access_problems(proxy_log.text(), path) == []


@pytest.mark.parametrize(
    ("listener", "path", "status"),
    [("auth", "/realms/eko/account/{u}", 403), ("app", "/{u}/openapi.json", 404)],
    ids=["403-account-console", "404-openapi"],
)
def test_adr0005_c4_proxy_access_log_refused_by_proxy(
    running: Started, proxy_log: Window, listener: str, path: str, status: int
) -> None:
    path = path.format(u=unique("refused"))
    assert send(running, listener, path).status_code == status
    assert access_problems(proxy_log.text(), path) == []


@pytest.mark.parametrize(
    ("label", "query", "cookie"),
    [
        ("empty-query", "", False),
        ("no-query", None, False),
        ("long-query", f"q={QUERY_MARKER}&pad=" + "z" * 9000, True),
        ("crlf", f"q={QUERY_MARKER}%0D%0A{{%22forged%22:1}}", True),
    ],
    # By label: the marker is random, and EKO-1-19 K-01 compares node IDs between sessions.
    ids=["empty-query", "no-query", "long-query", "crlf"],
)
def test_adr0005_c4_proxy_access_log_query_edges(
    running: Started, proxy_log: Window, label: str, query: str | None, cookie: bool
) -> None:
    path = f"/{unique(label)}%0D%0Aforged" if label == "crlf" else f"/{unique(label)}"
    send(running, "app", path, query=query, cookie=cookie)
    assert access_problems(proxy_log.text(), path.split("%")[0]) == []


def test_adr0005_c4_proxy_access_log_unmapped_host(running: Started, proxy_log: Window) -> None:
    path = f"/{unique('unmapped')}"
    send(running, "http", path, host=f"unmapped-{TOKEN}.invalid")
    text = proxy_log.text()
    mine, others = lines_for(text, path)
    assert others == [] and len(mine) <= 1, (mine, others)
    for line in mine:
        assert ll.proxy_line_problems(line, "proxy.access") == []
    assert ll.leaks(text, *MARKERS) == []


def test_adr0005_c4_proxy_access_log_upstream_failure(running: Started, proxy_log: Window) -> None:
    """Q-3 A: one access line and at most one error line; the error line's `msg` holds no request
    value (a marker there stops the work back to the addendum, fallback Q-3 B)."""
    composition = running.composition
    # Cut off from the network, not stopped: `compose start` would run migrate again and move
    # the start times test_k01_startup.py compares.
    container = composition.container_id("backend")
    network = f"{composition.project}_default"
    docker("network", "disconnect", network, container)
    try:
        path = f"/api/{unique('upstream')}"
        assert send(running, "app", path).status_code == 502
        text = proxy_log.text()
    finally:
        docker("network", "connect", "--alias", "backend", network, container)
        deadline = time.monotonic() + 120
        while composition.through_proxy("app", "/api/health").status_code != 200:
            assert time.monotonic() < deadline, "backend did not come back"
            time.sleep(1)
    assert access_problems(text, path) == []
    mine, _ = lines_for(text, path)
    errors = [line for line in mine if "size" not in line]
    assert len(errors) <= 1, errors
    for line in errors:
        assert ll.proxy_line_problems(line, "proxy.error") == []
        assert ll.leaks(str(line.get("msg")), *MARKERS, TOKEN) == [], line["msg"]


def test_adr0005_c4_proxy_access_log_contrast_default_format_fails() -> None:
    """Caddy's default access line for the same request, as Caddy 2.11 writes it unfiltered."""
    default = {
        "level": "info", "ts": 1.5, "logger": "http.log.access.log0",
        "msg": "handled request",
        "request": {"remote_ip": "172.18.0.1", "remote_port": "51000", "client_ip": "172.18.0.1",
                    "proto": "HTTP/1.1", "method": "GET", "host": "localhost",
                    "uri": f"/eko113-contrast?q={QUERY_MARKER}",
                    "headers": {"Cookie": [f"sid={COOKIE_MARKER}"], "X-Probe": [HEADER_MARKER]}},
        "bytes_read": 0, "user_id": "", "duration": 0.001, "size": 10, "status": 200,
        "resp_headers": {"Server": ["Caddy"]},
    }  # fmt: skip
    problems = access_problems(json.dumps(default), "/eko113-contrast")
    assert any(p.startswith("keys ") for p in problems), problems
    assert any(p.startswith("marker") for p in problems), problems
