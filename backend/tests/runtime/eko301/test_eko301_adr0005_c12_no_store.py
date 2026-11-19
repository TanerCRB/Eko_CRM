"""EKO-3-01, ADR-0005-C12 (second half): every customer response carries personal data or answers
for a record that may, so each one, refusals included, carries `Cache-Control: no-store` and no
validator (`ETag`, `Last-Modified`) a cache could reuse.
"""

import uuid

import httpx
import pytest

from tests.runtime.eko301.conftest import (
    CUSTOMERS,
    MANAGER,
    REP_A,
    REP_B,
    Crm,
    create,
    customer_url,
)

pytestmark = pytest.mark.runtime


def cache_headers(response: httpx.Response) -> tuple[list[str], str | None, str | None]:
    return (
        response.headers.get_list("cache-control"),
        response.headers.get("etag"),
        response.headers.get("last-modified"),
    )


def test_adr0005_c12_every_customer_response_is_no_store(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    made = create(rep_a, {"name": "Gospodarstwo Bez Pamieci"})
    customer_id = made.json()["id"]
    responses = {
        "201 create": made,
        "200 read": rep_a.send("GET", customer_url(customer_id)),
        "200 list": rep_a.send("GET", CUSTOMERS),
        "404 not visible": rep_b.send("GET", customer_url(customer_id)),
        "404 missing": rep_b.send("GET", customer_url(str(uuid.uuid4()))),
        "422 create": create(rep_a, {"name": ""}),
        "422 identifier": rep_a.send("GET", customer_url("x")),
        "403 manager create": create(crm.login(MANAGER, ["manager"]), {"name": "Gospodarstwo X"}),
    }
    statuses = {label: r.status_code for label, r in responses.items()}
    assert statuses == {label: int(label.split()[0]) for label in responses}
    for label, response in responses.items():
        assert cache_headers(response) == (["no-store"], None, None), label
