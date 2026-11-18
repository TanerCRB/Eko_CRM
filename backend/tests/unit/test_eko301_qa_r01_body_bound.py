"""EKO-3-01 fix round 1, QA contrasts for the build-time body bound of R-01 / B-01 (decision A on
Issue #195).

- `create_app()` refuses to build (the refusal logged, then `SystemExit`) when
  `REQUEST_BODY_LIMIT` is one byte below `LARGEST_CREATE_BODY`, and builds at exactly that limit.
- The largest create body whose every field passes its raw cap, every code point an astral
  character escaped as two `\\uXXXX`, fits `LARGEST_CREATE_BODY`; the same body with every key
  and the contact kind escaped as well still fits the shipped limit and reaches validation (422,
  not 413). The access dependency is overridden to a synthetic rep, so the request reaches the
  body.
"""

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any

import pytest

import app.main as main
from app.api.customers import LARGEST_CREATE_BODY
from app.auth.gate import authenticate
from app.domain import customers as rules
from app.domain.caller import Caller, Role

REP = Caller(subject="5a1e0301-0000-4000-8000-0000000000c1", name=None, roles=frozenset({Role.REP}))
ASTRAL = "\U0001f33e"


def test_qa_r01_the_app_refuses_to_build_with_a_limit_below_the_largest_body(
    backend_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(main, "REQUEST_BODY_LIMIT", LARGEST_CREATE_BODY - 1)
    with pytest.raises(SystemExit):
        main.create_app()
    refusals = [r.exc_info[1] for r in caplog.records if r.exc_info and r.exc_info[1]]
    assert [str(e) for e in refusals] == ["the request body limit refuses a valid customer"]


def test_qa_r01_contrast_the_app_builds_with_the_limit_at_the_largest_body(
    backend_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "REQUEST_BODY_LIMIT", LARGEST_CREATE_BODY)
    main.create_app()


def largest_body() -> dict[str, Any]:
    contact = {
        "kind": "email",
        "value": ASTRAL * rules.VALUE_RAW_LIMIT,
        "note": ASTRAL * rules.NOTE_RAW_LIMIT,
        "primary": False,
    }
    return {
        "name": ASTRAL * rules.NAME_RAW_LIMIT,
        "country": rules.DEFAULT_COUNTRY,
        "contacts": [contact] * rules.CONTACT_LIMIT,
    }


def escaped_keys(encoded: bytes) -> bytes:
    for word in ("name", "country", "contacts", "kind", "value", "note", "primary", "email"):
        escaped = "".join(f"\\u{ord(c):04x}" for c in word)
        encoded = encoded.replace(f'"{word}"'.encode(), f'"{escaped}"'.encode())
    return encoded


def test_qa_r01_the_largest_raw_capped_body_fits_the_derived_bound() -> None:
    encoded = json.dumps(largest_body()).encode("ascii")
    assert len(encoded) <= LARGEST_CREATE_BODY, (len(encoded), LARGEST_CREATE_BODY)


def post(body: bytes) -> int:
    app = main.create_app()
    app.dependency_overrides[authenticate] = lambda: REP
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

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
        "headers": [
            (b"host", b"app.test"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("app.test", 443),
    }
    asyncio.run(app(scope, receive, send))
    status: int = next(m for m in sent if m["type"] == "http.response.start")["status"]
    return status


def test_qa_r01_the_largest_raw_capped_body_with_escaped_keys_reaches_validation(
    backend_env: None,
) -> None:
    encoded = escaped_keys(json.dumps(largest_body()).encode("ascii"))
    assert json.loads(encoded) == largest_body()
    assert post(encoded) == 422
