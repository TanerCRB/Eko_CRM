"""EKO-4-01 K-01 (d) (ADR-0006 *Visit identifiers are never reused*; the ADR-0005-C17 pattern of
`test_eko301_backup_customers.py`; gate 1 A-1 A): visits are planned after a backup set was taken;
the database is restored from the set into an empty server, visits are planned there through the
application's own store (`app.data.visits.VisitStore`), and none of their identifiers is one issued
after the set, nor before it. The restored schema holds no sequence and no identifier default on the
visit table, so no database state can hand an identifier out again. Every value is synthetic.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.data.visits import VisitStore
from app.domain.ownership import OwnedBy
from app.domain.visits import Visit, VisitDraft
from tests.runtime.backup_lab import BackupLab, open_set, restore_psql, restore_set, set_names
from tests.runtime.test_eko301_backup_customers import published_server, store_on

pytestmark = pytest.mark.runtime

OWNER = "5a1e0401-0000-4000-8000-0000000000c7"
STARTS = datetime(2026, 11, 30, 9, 0, tzinfo=UTC)


def plant_visit(backup_lab: BackupLab, customer_id: str) -> str:
    """A visit as the application stores one, with a random UUIDv4 identifier."""
    visit_id = str(uuid.uuid4())
    # The instants are fixed literals: the monitor session takes variables of a narrow form only.
    backup_lab.sql(
        "INSERT INTO visit (id, customer_id, owner_subject, starts_at, ends_at) "
        "VALUES (CAST(:'v' AS uuid), CAST(:'c' AS uuid), :'o', "
        "'2026-11-30T09:00:00Z', '2026-11-30T10:00:00Z')",
        v=visit_id,
        c=customer_id,
        o=OWNER,
    )
    return visit_id


def test_k01_no_visit_identifier_is_issued_twice_after_a_restore(backup_lab: BackupLab) -> None:
    backup_lab.lab.at_head()
    [[revision]] = backup_lab.sql("SELECT version_num FROM alembic_version")
    assert revision == "0010"
    customer_id = backup_lab.plant_customer(OWNER)
    before = {plant_visit(backup_lab, customer_id) for _ in range(3)}
    names_before = set_names(backup_lab.double)
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - names_before
    contents = open_set(backup_lab.double, name, backup_lab.identity)
    after = {plant_visit(backup_lab, customer_id) for _ in range(5)}
    assert after.isdisjoint(before)
    with published_server() as (container, port, password):
        restore_set(container, contents)
        restored = {
            row[0] for row in restore_psql(container, "eko", "SELECT CAST(id AS text) FROM visit")
        }
        assert restored == before, "the restored set holds exactly the visits before it"
        assert restore_psql(
            container,
            "eko",
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'S'",
        ) == [["app_session_id_seq"]], "only revision 0003's session identity has a sequence"
        assert (
            restore_psql(
                container,
                "eko",
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'visit' "
                "AND (column_default IS NOT NULL OR is_identity = 'YES')",
            )
            == []
        )
        _, database = store_on(port, password)
        try:
            store = VisitStore(database)
            draft = VisitDraft(
                customer_id=uuid.UUID(customer_id),
                starts_at=STARTS,
                ends_at=STARTS + timedelta(hours=1),
                own_address=None,
            )
            made = set()
            for _ in range(5):
                planned = store.create(OwnedBy(OWNER), draft)
                assert isinstance(planned, Visit), planned
                made.add(str(planned.id))
        finally:
            database.dispose()
        assert made.isdisjoint(after), "an identifier issued after the set was issued again"
        assert made.isdisjoint(before)
        assert all(uuid.UUID(identifier).version == 4 for identifier in made)
