"""EKO-3-02 K-01, limit edge (fix round 1 of EKO-3-01, R-01 A, carried forward): the largest create
body whose every field, the new address and tax-ID fields included, sits at its raw cap with each
character an astral one written as two `\\uXXXX` escapes, fits `LARGEST_CREATE_BODY`, which fits
the 2 MiB request body limit; so a valid customer is never refused for its size.
"""

import json
from typing import Any

from app import main
from app.api.customers import LARGEST_CREATE_BODY
from app.domain import customers as rules

ASTRAL = "\U0001f33e"
NEW_RAW_CAPS = {
    "street": rules.STREET_RAW_LIMIT,
    "postal_code": rules.POSTAL_CODE_RAW_LIMIT,
    "town": rules.TOWN_RAW_LIMIT,
    "voivodeship": rules.REGION_RAW_LIMIT,
    "county": rules.REGION_RAW_LIMIT,
    "tax_id": rules.TAX_ID_RAW_LIMIT,
}


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
        **{field: ASTRAL * cap for field, cap in NEW_RAW_CAPS.items()},
        "contacts": [contact] * rules.CONTACT_LIMIT,
    }


def test_k01_the_largest_raw_capped_body_with_the_address_fits_the_bound() -> None:
    encoded = json.dumps(largest_body()).encode("ascii")
    without = json.dumps({k: v for k, v in largest_body().items() if k not in NEW_RAW_CAPS})
    assert len(encoded) - len(without) > 12 * sum(NEW_RAW_CAPS.values())
    assert len(encoded) <= LARGEST_CREATE_BODY, (len(encoded), LARGEST_CREATE_BODY)
    assert LARGEST_CREATE_BODY <= main.REQUEST_BODY_LIMIT
