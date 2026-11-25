"""EKO-3-06 K-01 (SEED-1, ACC-4, PRH-4; ADR-0003-C39, ADR-0005-C23): the load gives each named
rep exactly its share of the committed dataset, and each rep sees exactly that share through the
API. Visibility itself is the data-layer scope's (capabilities row 46); it is read here as the
observable, not proven again.

- Each share's stored `owner_subject` is its named subject; rep A's list is exactly A's share
  (ids and values), as for B and C, and the manager's list is all three; B's record read by A
  answers byte-equal to an id that exists nowhere.
- The stored value set equals the committed fingerprint, and two runs of `python -m app.seed`
  into two fresh databases, at two instants and under two hash seeds, store the same set.
- Subjects not of the owner form, a wrong count or a repeated subject are refused before
  anything is loaded (G-3 A); subjects that differ only in case are distinct.

Contrast: the same run with only B replaced by B' puts B's share under B'; B sees nothing and
those records answer 404 to B; A's and C's shares are unchanged.
"""

import uuid
from typing import Any

import pytest

from app.seed_dataset import SHARE_SIZE
from tests.runtime.eko301.conftest import CUSTOMERS, MANAGER, Crm, customer_url
from tests.runtime.eko303.conftest import rows_of, same_answer
from tests.runtime.eko306.conftest import (
    SEED_A,
    SEED_B,
    SEED_B_PRIME,
    SEED_C,
    SUBJECTS,
    Seeder,
    fresh_database,
    seed_process,
    seeded,
    snapshot,
)
from tests.support.eko306_dataset import CANONICAL_ROWS, FINGERPRINT, fingerprint, stored_rows
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

SHARE_PREFIX = {SEED_A: "seed-v1-1-", SEED_B: "seed-v1-2-", SEED_C: "seed-v1-3-"}


def listed(crm: Crm, subject: str, roles: list[str]) -> list[dict[str, Any]]:
    response = crm.login(subject, roles).send("GET", CUSTOMERS)
    assert response.status_code == 200, response.text[:300]
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def share_items(crm: Crm, owner: str) -> list[dict[str, Any]]:
    rows = rows_of(
        crm.pg,
        "eko",
        "SELECT id::text, name, country FROM customer WHERE owner_subject = %s ORDER BY id",
        (owner,),
    )
    return [{"id": i, "name": n, "country": c} for i, n, c in rows]


def test_k01_each_share_is_stored_under_its_named_subject_and_seen_by_it_only(
    crm: Crm, seed: Seeder
) -> None:
    run = seed()
    assert run.code == 0, run.lines
    stored = seeded(crm.pg)
    assert len(stored) == 3 * SHARE_SIZE
    for subject, prefix in SHARE_PREFIX.items():
        keys = [key for _, key, owner in stored if owner == subject]
        assert len(keys) == SHARE_SIZE
        assert all(key.startswith(prefix) for key in keys)

    for subject in SUBJECTS:
        expected = share_items(crm, subject)
        assert len(expected) == SHARE_SIZE
        assert sorted(listed(crm, subject, ["rep"]), key=lambda i: i["id"]) == expected
    every = sorted(listed(crm, MANAGER, ["manager"]), key=lambda i: i["id"])
    assert every == sorted(sum((share_items(crm, s) for s in SUBJECTS), []), key=lambda i: i["id"])

    rep_a = crm.login(SEED_A, ["rep"])
    [b_record] = [i for i, key, owner in stored if owner == SEED_B][:1]
    assert same_answer(
        rep_a.send("GET", customer_url(b_record)),
        rep_a.send("GET", customer_url(str(uuid.uuid4()))),
    )
    assert rep_a.send("GET", customer_url(b_record)).status_code == 404
    rows = stored_rows(rows_of(crm.pg, "eko", CANONICAL_ROWS))
    assert fingerprint(rows) == FINGERPRINT


def test_k01_two_processes_into_two_fresh_databases_store_the_same_value_set(pg: Postgres) -> None:
    prints = []
    for database, hash_seed in (("eko306_k01_first", "1"), ("eko306_k01_second", "31337")):
        fresh_database(pg, database)
        done = seed_process(pg, database=database, hash_seed=hash_seed)
        assert done.returncode == 0, done.stderr[-2000:]
        prints.append(fingerprint(stored_rows(rows_of(pg, database, CANONICAL_ROWS))))
    assert prints == [FINGERPRINT, FINGERPRINT]


def test_k01_contrast_b_replaced_by_b_prime_moves_only_b_share(crm: Crm, seed: Seeder) -> None:
    run = seed((SEED_A, SEED_B_PRIME, SEED_C))
    assert run.code == 0, run.lines
    stored = seeded(crm.pg)
    owners = {owner for _, key, owner in stored if key.startswith("seed-v1-2-")}
    assert owners == {SEED_B_PRIME}
    assert listed(crm, SEED_B, ["rep"]) == []
    rep_b = crm.login(SEED_B, ["rep"])
    for record_id, _, _ in [r for r in stored if r[2] == SEED_B_PRIME][:5]:
        assert rep_b.send("GET", customer_url(record_id)).status_code == 404
    assert len(listed(crm, SEED_B_PRIME, ["rep"])) == SHARE_SIZE
    for subject, prefix in ((SEED_A, "seed-v1-1-"), (SEED_C, "seed-v1-3-")):
        assert {key[: len(prefix)] for _, key, o in stored if o == subject} == {prefix}
    assert fingerprint(stored_rows(rows_of(crm.pg, "eko", CANONICAL_ROWS))) == FINGERPRINT


SUBJECT_REFUSALS = {
    "an-empty-subject": (SEED_A, "", SEED_C),
    "a-subject-with-a-space": (SEED_A, "rep b", SEED_C),
    "a-non-ascii-subject": (SEED_A, "rep-ł", SEED_C),
    "a-256-character-subject": (SEED_A, "b" * 256, SEED_C),
    "two-subjects": (SEED_A, SEED_B),
    "four-subjects": (SEED_A, SEED_B, SEED_C, SEED_B_PRIME),
    "a-repeated-subject": (SEED_A, SEED_B, SEED_A),
}


@pytest.mark.parametrize("case", sorted(SUBJECT_REFUSALS))
def test_k01_edge_subjects_outside_the_rule_are_refused_before_anything_is_loaded(
    crm: Crm, seed: Seeder, case: str
) -> None:
    before = snapshot(crm.pg)
    run = seed(SUBJECT_REFUSALS[case])
    assert run.code != 0
    assert run.refusal is not None and "subject" in run.refusal
    assert snapshot(crm.pg) == before


def test_k01_edge_subjects_that_differ_only_in_case_are_three_distinct_owners(
    crm: Crm, seed: Seeder
) -> None:
    subjects = ("Rep-Eko306", "rep-eko306", "REP-EKO306")
    run = seed(subjects)
    assert run.code == 0, run.lines
    owners = [owner for _, _, owner in seeded(crm.pg)]
    assert {s: owners.count(s) for s in subjects} == dict.fromkeys(subjects, SHARE_SIZE)
