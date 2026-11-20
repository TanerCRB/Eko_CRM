"""EKO-3-04 carriers: EKO-3-01's (the shipped `create_app()` on real PostgreSQL 18 and the local
OIDC stub, a real session per synthetic staff member), bound here by name, and the readers of a
searched or filtered list. Every value is synthetic (ADR-0005): invented names and towns,
`example.com` addresses, phones from an obviously fictitious range.
"""

from typing import Any

import httpx

from tests.runtime.eko201.conftest import Browser
from tests.runtime.eko301 import conftest as eko301
from tests.runtime.eko301.conftest import CUSTOMERS, created_id

pg = eko301.pg
clean = eko301.clean
stub = eko301.stub
clock = eko301.clock
make_app = eko301.make_app
browser_for = eko301.browser_for
clean_customers = eko301.clean_customers
crm = eko301.crm

CORRELATION = "eko-correlation-id"
# A well-formed subject that owns nothing and never logged in.
NOBODY = "5a1e0304-0000-4000-8000-0000000000ee"
EMPTY: dict[str, list[Any]] = {"items": []}


def search(browser: Browser, params: Any = None) -> httpx.Response:
    """The list with query parameters; `params` may be a list of pairs, to repeat or order them."""
    return browser.send("GET", CUSTOMERS, params=params)


def found(browser: Browser, params: Any = None) -> set[str]:
    response = search(browser, params)
    assert response.status_code == 200, response.text[:300]
    return {item["id"] for item in response.json()["items"]}


def listed_items(browser: Browser, params: Any = None) -> list[dict[str, Any]]:
    response = search(browser, params)
    assert response.status_code == 200, response.text[:300]
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def answer(response: httpx.Response) -> tuple[int, bytes, list[tuple[str, str]]]:
    """Status, body and headers but `Eko-Correlation-Id`: "byte-equal" (ADR-0003-C33)."""
    headers = sorted((k.lower(), v) for k, v in response.headers.multi_items())
    return response.status_code, response.content, [h for h in headers if h[0] != CORRELATION]


def customer(browser: Browser, name: str, **fields: Any) -> str:
    return created_id(browser, {"name": name, **fields})


def phone(value: str, note: str | None = None) -> dict[str, Any]:
    return {"kind": "phone", "value": value, "note": note}


def email(value: str, note: str | None = None) -> dict[str, Any]:
    return {"kind": "email", "value": value, "note": note}
