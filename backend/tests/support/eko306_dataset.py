"""EKO-3-06: one canonical form of the seed's value set, built the same way from the dataset's
drafts and from the rows PostgreSQL stores, and its committed fingerprint (K-01, ADR-0005-C23).

The canonical form holds every customer and contact field but the identifiers and the owner,
ordered by dataset key and contacts by position. The fingerprint is a SHA-256 digest of its JSON,
so no committed line carries a dataset value (A-1 A: a digest, not the values).
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

from app.domain.customers import CustomerDraft, customer_draft
from app.seed_dataset import Record, records

# The digest of the dataset `seed-v1`; a change to any generated value changes it.
FINGERPRINT = "181284bdae68a04166162265ebf1f30acba4022c1270eaa7ad0f905cf34cf214"

CANONICAL_ROWS = """
SELECT c.dataset_key, c.name, c.country, c.street, c.postal_code, c.town, c.voivodeship,
       c.county, c.nip, c.foreign_tax_id,
       COALESCE(json_agg(json_build_array(k.kind, k.value, k.note, k.is_primary)
                ORDER BY k.position) FILTER (WHERE k.id IS NOT NULL), '[]'::json)
FROM customer c LEFT JOIN customer_contact k ON k.customer_id = c.id
WHERE c.dataset_key IS NOT NULL
GROUP BY c.id
ORDER BY c.dataset_key
"""


def draft_row(key: str, draft: CustomerDraft) -> list[Any]:
    address = draft.address
    return [
        key,
        draft.name,
        draft.country,
        address.street,
        address.postal_code,
        address.town,
        address.voivodeship,
        address.county,
        draft.tax_id.nip,
        draft.tax_id.foreign,
        [[c.kind.value, c.value, c.note, c.primary] for c in draft.contacts],
    ]


def dataset_rows(found: Sequence[Record] | None = None) -> list[list[Any]]:
    chosen = records() if found is None else found
    rows = [draft_row(r.key, customer_draft(r.customer)) for r in chosen]
    return sorted(rows, key=lambda row: str(row[0]))


def stored_rows(rows: Iterable[Sequence[Any]]) -> list[list[Any]]:
    return [[*row[:10], [list(contact) for contact in row[10]]] for row in rows]


def fingerprint(rows: list[list[Any]]) -> str:
    text = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
