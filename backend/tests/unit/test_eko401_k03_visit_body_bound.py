"""EKO-4-01, the visit create joins the build-time body bound (ADR-0003 gate-2 rules of 2026-11-17,
"The application refuses to build when the largest valid request body is larger than the limit";
the impact map's "the visit body joins the 2 MiB build check"): the largest visit body whose every
field sits at its raw cap, each character an astral one escaped as two `\\uXXXX`, fits
`LARGEST_VISIT_BODY`, which fits the 2 MiB limit, and `create_app()` refuses to build when the
limit is one byte below it.
"""

import json
import uuid
from typing import Any

import pytest

import app.main as main
from app.api.visits import LARGEST_VISIT_BODY
from app.domain import visits as rules

ASTRAL = "\U0001f33e"


def largest_body() -> dict[str, Any]:
    at = {"date": "2026-11-30", "time": "10:00"}
    return {
        "customer_id": str(uuid.uuid4()),
        "start": at,
        "end": at,
        "own_address": ASTRAL * rules.OWN_ADDRESS_RAW_LIMIT,
    }


def escaped_keys(encoded: bytes) -> bytes:
    """The same body with every key written as `\\uXXXX` escapes, as JSON allows."""
    for word in ("customer_id", "start", "end", "own_address", "date", "time"):
        escaped = "".join(f"\\u{ord(c):04x}" for c in word)
        encoded = encoded.replace(f'"{word}"'.encode(), f'"{escaped}"'.encode())
    return encoded


def test_k03_edge_the_largest_raw_capped_visit_body_fits_the_derived_bound() -> None:
    body = largest_body()
    # The longest form of an identifier the request model accepts.
    body["customer_id"] = f"urn:uuid:{body['customer_id']}"
    plain = json.dumps(body).encode("ascii")
    encoded = escaped_keys(plain)
    assert len(encoded) > len(plain) > 12 * rules.OWN_ADDRESS_RAW_LIMIT
    assert len(encoded) <= LARGEST_VISIT_BODY, (len(encoded), LARGEST_VISIT_BODY)
    assert LARGEST_VISIT_BODY <= main.REQUEST_BODY_LIMIT


def test_k03_edge_the_app_refuses_to_build_with_a_limit_below_the_largest_visit_body(
    backend_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The customer bound is larger; set aside here so the visit's own check is the one reached.
    monkeypatch.setattr(main, "LARGEST_CREATE_BODY", 0)
    monkeypatch.setattr(main, "REQUEST_BODY_LIMIT", LARGEST_VISIT_BODY - 1)
    with pytest.raises(SystemExit):
        main.create_app()
    refusals = [r.exc_info[1] for r in caplog.records if r.exc_info and r.exc_info[1]]
    assert [str(e) for e in refusals] == ["the request body limit refuses a valid visit"]


def test_k03_edge_contrast_the_app_builds_with_the_limit_at_the_largest_visit_body(
    backend_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "LARGEST_CREATE_BODY", 0)
    monkeypatch.setattr(main, "REQUEST_BODY_LIMIT", LARGEST_VISIT_BODY)
    main.create_app()
