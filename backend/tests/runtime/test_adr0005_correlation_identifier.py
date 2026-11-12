"""EKO-1-13 K-03, correlation identifier: `backend` generates one per request, 32 lower-case
hexadecimal digits, never from a client value; every line of the request carries it and every
response returns it in `Eko-Correlation-Id`, unchanged through `proxy` (ADR-0005 addendum of
2026-11-02, *The correlation identifier*, Q-4 A).

Run against the composition's `backend` with its two uvicorn workers. Contrast (a): requests
sent with `X-Request-ID`, `X-Correlation-ID`, `traceparent` and `Eko-Correlation-Id` set to
markers get an identifier equal to none of them, and two identical requests get different ones.
"""

import json
import secrets
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from tests.runtime.conftest import Started
from tests.runtime.eko113 import window
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
CLIENT_IDS = {
    "X-Request-ID": f"marker-xrid-{TOKEN}",
    "X-Correlation-ID": f"marker-xcid-{TOKEN}",
    "traceparent": f"00-{TOKEN * 3}aa-{TOKEN}abcdef-01",
    "Eko-Correlation-Id": secrets.token_hex(16),
}


def through(started: Started, path: str, headers: list[tuple[str, str]]) -> httpx.Response:
    env = started.composition.env
    with httpx.Client(verify=False, timeout=15) as client:
        request = client.build_request(
            "GET",
            httpx.URL(
                scheme="https",
                host="127.0.0.1",
                port=int(env["PROXY_HTTPS_PORT"]),
                raw_path=path.encode(),
            ),  # fmt: skip
            headers=[("Host", env["APP_HOST"]), *headers],
        )
        request.extensions["sni_hostname"] = env["APP_HOST"]
        return client.send(request)


def test_adr0005_correlation_identifier(running: Started) -> None:
    mark = window(running.composition, "backend")
    headers = [*CLIENT_IDS.items(), ("X-Request-ID", f"second-{TOKEN}")]
    first = through(running, "/api/health", headers)
    second = through(running, "/api/health", headers)
    missing = through(running, f"/api/marker-{TOKEN}", headers)
    lines, others = ll.json_lines(mark.text())
    assert others == []
    ids = []
    for response in (first, second, missing):
        cid = response.headers.get("eko-correlation-id", "")
        assert ll.CORRELATION_ID.fullmatch(cid), response.headers
        assert response.headers.get_list("eko-correlation-id") == [cid]
        assert cid not in CLIENT_IDS.values() and TOKEN not in cid
        assert [line["event"] for line in lines if line.get("correlation_id") == cid] == ["request"]
        ids.append(cid)
    assert len(set(ids)) == 3
    assert ll.leaks(json.dumps(lines), TOKEN) == []


def test_adr0005_correlation_identifier_concurrent_on_two_workers(running: Started) -> None:
    mark = window(running.composition, "backend")
    with ThreadPoolExecutor(max_workers=16) as pool:
        responses = list(pool.map(lambda _: through(running, "/api/health", []), range(48)))
    lines, _ = ll.json_lines(mark.text(settle=2))
    ids = [r.headers["eko-correlation-id"] for r in responses]
    assert len(set(ids)) == len(ids)
    by_id = {line["correlation_id"]: line for line in lines if line.get("event") == "request"}
    assert set(ids) <= set(by_id), "a response's identifier is on no request line"
    assert all(by_id[cid]["status"] == r.status_code for cid, r in zip(ids, responses, strict=True))
