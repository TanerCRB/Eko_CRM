"""EKO-1-13 K-02, `frontend` half: an SPA request through `proxy` with a query marker leaves
`frontend`'s log with no line for it, or one line under `proxy`'s rule holding no marker (ADR-0005
addendum of 2026-11-02, *`frontend`*). Its own lines (start, stop) are JSON under the same field
restriction.

Contrast: a `frontend` line written with the request URL (Caddy's default access line) is found by
the same check.
"""

import json
import secrets

import pytest

from tests.runtime.conftest import Started
from tests.runtime.eko113 import container_log, window
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
MARKER = f"marker-spa-{TOKEN}"


def frontend_problems(text: str, path: str) -> list[str]:
    objects, others = ll.json_lines(text)
    problems = [f"not JSON: {line[:200]!r}" for line in others]
    mine = [o for o in objects if path in json.dumps(o)]
    if len(mine) > 1:
        problems.append(f"{len(mine)} lines for one request")
    problems += [p for line in mine for p in ll.proxy_line_problems(line, "proxy.access")]
    problems += [f"marker {m}" for m in ll.leaks(text, MARKER)]
    return problems


def test_adr0005_frontend_request_log(running: Started) -> None:
    mark = window(running.composition, "frontend")
    path = f"/eko113-spa-{TOKEN}"
    response = running.composition.through_proxy(
        "app", f"{path}?q={MARKER}", headers={"Cookie": f"sid={MARKER}", "X-Probe": MARKER}
    )
    assert response.status_code == 200
    assert frontend_problems(mark.text(), path) == []


def test_adr0005_frontend_own_lines_are_json(running: Started) -> None:
    objects, others = ll.json_lines(container_log(running.composition.container_id("frontend")))
    assert objects, "frontend wrote no line at all"
    assert others == [], others[:5]
    for line in objects:
        assert {"headers", "resp_headers", "remote_ip", "remote_port"}.isdisjoint(
            ll.flatten(line).keys() | {k.rsplit(".", 1)[-1] for k in ll.flatten(line)}
        ), line


def test_adr0005_frontend_request_log_contrast_full_url_line_fails() -> None:
    path = f"/eko113-spa-{TOKEN}"
    line = {"level": "info", "ts": "2026-11-02T10:00:00.000000000Z", "logger": "http.log.access",
            "msg": "handled request", "request": {"client_ip": "172.18.0.5", "method": "GET",
            "host": "frontend:8080", "uri": f"{path}?q={MARKER}"}, "duration": 0.001,
            "size": 400, "status": 200}  # fmt: skip
    problems = frontend_problems(json.dumps(line), path)
    assert any(p.startswith("marker") for p in problems), problems
