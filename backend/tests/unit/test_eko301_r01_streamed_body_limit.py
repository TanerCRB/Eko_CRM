"""EKO-3-01 fix round 1, R-01 / B-01 (decision A on Issue #195), at the ASGI level: a body that
arrives as many `http.request` messages with no `Content-Length` is counted as it arrives and
refused with 413 once it passes `REQUEST_BODY_LIMIT`, without the rest being read. A stated
`Content-Length` past the limit is refused before any byte is read. The access dependency is
overridden to a synthetic rep, so the request reaches the body.
"""

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any

from app.auth.gate import authenticate
from app.domain.caller import Caller, Role
from app.main import REQUEST_BODY_LIMIT, create_app

REP = Caller(subject="5a1e0301-0000-4000-8000-0000000000b1", name=None, roles=frozenset({Role.REP}))
CHUNK = 64 * 1024


def _as_rep() -> Caller:
    return REP


def call(headers: list[tuple[bytes, bytes]], messages: int) -> tuple[int, Any, int]:
    """(status, body, chunks read) for a POST /api/customers of `messages` chunks."""
    app = create_app()
    app.dependency_overrides[authenticate] = _as_rep
    read = 0
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal read
        if read >= messages:
            return {"type": "http.disconnect"}
        read += 1
        body = b'{"name":"G"' if read == 1 else b" " * CHUNK
        return {"type": "http.request", "body": body, "more_body": read < messages}

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(dict(message))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/customers",
        "raw_path": b"/api/customers",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"app.test"), (b"content-type", b"application/json"), *headers],
        "client": ("127.0.0.1", 1),
        "server": ("app.test", 443),
    }
    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(body), read


def test_r01_a_streamed_body_past_the_limit_is_cut_off_while_it_arrives(backend_env: None) -> None:
    total = REQUEST_BODY_LIMIT // CHUNK + 20
    status, body, read = call([], total)
    assert (status, body) == (413, {"detail": "request body too large"})
    assert read < total, "the whole body was read before the refusal"


def test_r01_a_stated_length_past_the_limit_is_refused_before_reading(backend_env: None) -> None:
    length = str(REQUEST_BODY_LIMIT + 1).encode()
    status, body, read = call([(b"content-length", length)], 3)
    assert (status, body) == (413, {"detail": "request body too large"})
    assert read == 0


def test_r01_contrast_a_small_streamed_body_reaches_validation(backend_env: None) -> None:
    status, body, _ = call([], 3)
    assert status == 422, body
