"""The operator seed (SEED-1; EKO-3-06): `python -m app.seed <subject> <subject> <subject>`.

In an environment it runs only as a one-off of `worker`, with that service's environment
(ADR-0004 addendum of EKO-3-06, C37):
`docker compose run --rm --no-deps worker python -m app.seed <subject> <subject> <subject>`.

Before anything is written, in this order, a run is refused with a non-zero exit unless:
1. the target declares itself synthetic-only (ADR-0005 addendum of EKO-3-06, C22);
2. it names exactly three distinct subjects of the owner form, the owners of the dataset's three
   shares in order (G-3 A; ADR-0003 addendum of EKO-3-06, C39);
3. the database is at the code's head or a recorded descendant (G-7 A); the seed never migrates.

Each record then becomes a draft through create's own rules and is loaded in a transaction of
its own, through one database connection at most (ADR-0003-C19 as restated). A record already
loaded is skipped (its dataset key decides, A-2 A); one that create's rules or the NIP's
uniqueness refuse is reported and not loaded, and the run ends non-success. The report names a
record by its dataset key and rule only, never a customer value, a validation error's input or a
driver message (ADR-0005 *What may appear in logs*, C23). The seed builds no caller, reads no
clock and calls no identity server; it writes no staff display-name copy.
"""

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from app import seed_dataset
from app.core.logs import install_process_logging
from app.core.settings import SYNTHETIC_DATA_DECLARATION, SeedSettings, load_settings
from app.data.customers import CustomerStore
from app.data.database import Database
from app.data.schema_revision import refuse_unless_servable
from app.data.sessions import StorageUnavailable
from app.domain.customers import CONTACTS_FIELD, CustomerRefused, NipTaken, customer_draft
from app.domain.ownership import OWNER_LIMIT, OwnedBy, operator_creation_scope
from app.seed_dataset import SHARES, Record

logger = logging.getLogger("app.seed")

PROCESS = "seed"
# The one connection ADR-0003-C19 counts for the seed: a pool of one and no overflow.
SEED_CONNECTIONS = 1
# The rule family a refused field falls under (SEED-1's "CUS-2 to CUS-8", K-03).
FAMILIES = {
    "name": "CUS-2",
    "country": "CUS-2",
    "street": "CUS-3/CUS-4",
    "postal_code": "CUS-3/CUS-4",
    "town": "CUS-3/CUS-4",
    "voivodeship": "CUS-3/CUS-4",
    "county": "CUS-3/CUS-4",
    "tax_id": "CUS-5",
    f"{CONTACTS_FIELD}.kind": "CUS-8",
    f"{CONTACTS_FIELD}.value": "CUS-8",
    f"{CONTACTS_FIELD}.note": "CUS-1",
    CONTACTS_FIELD: "CUS-1",
}
NIP_TAKEN = ("CUS-6", "tax_id")


@dataclass
class Outcome:
    total: int
    added: int = 0
    already: int = 0
    refused: int = 0
    stopped: bool = False

    @property
    def complete(self) -> bool:
        return not self.stopped and self.refused == 0


def _refused(key: str, rules: Sequence[tuple[str, str]]) -> None:
    named = ", ".join(f"{family} ({field})" for family, field in rules)
    logger.warning("record %s refused: %s", key, named)


def load(store: CustomerStore, scopes: Sequence[OwnedBy], records: Sequence[Record]) -> Outcome:
    """Every record in order, each in a transaction of its own; a refusal never stops the run."""
    outcome = Outcome(total=len(records))
    for record in records:
        try:
            draft = customer_draft(record.customer)
        except CustomerRefused as refused:
            _refused(record.key, [(FAMILIES[field], field) for field in refused.fields])
            outcome.refused += 1
            continue
        try:
            added = store.load(scopes[record.share], record.key, draft)
        except NipTaken:
            _refused(record.key, [NIP_TAKEN])
            outcome.refused += 1
            continue
        except StorageUnavailable:
            logger.error("seed stopped: the database is unavailable")
            outcome.stopped = True
            return outcome
        if added:
            outcome.added += 1
        else:
            outcome.already += 1
    return outcome


def _scopes(subjects: Sequence[str]) -> tuple[OwnedBy, ...]:
    """The creation scope of each share; the subjects themselves are never repeated in output."""
    refusal = (
        f"{PROCESS} refused to start: name exactly {SHARES} distinct owner subjects "
        f"(1 to {OWNER_LIMIT} printable ASCII characters each)"
    )
    if len(subjects) != SHARES or len(set(subjects)) != SHARES:
        raise SystemExit(refusal)
    try:
        return tuple(operator_creation_scope(subject) for subject in subjects)
    except ValueError:
        raise SystemExit(refusal) from None


def run(subjects: Sequence[str], records: Sequence[Record] | None = None) -> int:
    """The seed's exit status: 0 when every record is loaded or already loaded, else 1. A run
    refused before any write raises `SystemExit` with the reason. `records` replaces the
    committed dataset in tests only (C-4 A)."""
    settings = load_settings(SeedSettings)
    if not settings.declares_synthetic_data_only():
        raise SystemExit(
            f"{PROCESS} refused to start: the target is not declared synthetic-only "
            f"({SYNTHETIC_DATA_DECLARATION} does not hold the accepted value)"
        )
    scopes = _scopes(subjects)
    refuse_unless_servable(settings, PROCESS)
    bounded = settings.model_copy(
        update={"app_db_pool_size": SEED_CONNECTIONS, "app_db_max_overflow": 0}
    )
    database = Database.from_settings(bounded)
    try:
        chosen = seed_dataset.records() if records is None else records
        outcome = load(CustomerStore(database), scopes, chosen)
    finally:
        database.dispose()
    summary = (
        f"{outcome.total} records, {outcome.added} added, {outcome.already} already loaded, "
        f"{outcome.refused} refused"
    )
    if outcome.stopped:
        logger.error("seed stopped before the end: %s so far", summary)
        return 1
    logger.info("seed finished: %s%s", summary, "; nothing was added" if outcome.added == 0 else "")
    return 0 if outcome.complete else 1


def main() -> None:
    install_process_logging("worker")
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
